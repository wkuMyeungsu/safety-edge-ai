"""uploader: gateway가 넘긴 위반 판정 + 사진을 Supabase에 저장한다.

계약: docs/contracts/record-storage.md, docs/contracts/storage.md
받은 기록은 먼저 BUFFER_DIR에 파일로 남긴다 (사진 {id}.jpg, 기록 {id}.json).
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

SERVICE = os.environ.get("SERVICE_NAME", "uploader")
BUFFER_DIR = Path(os.environ.get("BUFFER_DIR", "/buffer"))

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # violations 버킷 제한과 같다
DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

logging.basicConfig(level=logging.INFO, format="%(asctime)s uploader %(levelname)s %(message)s")
log = logging.getLogger("uploader")

app = FastAPI()


class BadRecord(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


@app.exception_handler(BadRecord)
async def bad_record(_: Request, e: BadRecord):
    log.warning("거부 %d: %s", e.status, e.detail)
    return JSONResponse({"status": "rejected", "detail": e.detail}, status_code=e.status)


@app.exception_handler(RequestValidationError)
async def missing_part(_: Request, e: RequestValidationError):
    # result·image 파트가 빠진 경우. 계약상 422가 아니라 400
    return JSONResponse({"status": "rejected", "detail": "result와 image 파트가 필요함"}, status_code=400)


def parse_result(text: str) -> dict:
    """result JSON을 검사해 safety_logs 한 행으로 바꾼다. 표에 없는 필드는 버린다."""
    try:
        r = json.loads(text)
    except json.JSONDecodeError:
        raise BadRecord(400, "result가 JSON이 아님")
    if not isinstance(r, dict):
        raise BadRecord(400, "result는 JSON 객체여야 함")

    device_id = r.get("device_id")
    if not isinstance(device_id, str) or not DEVICE_ID.match(device_id):
        raise BadRecord(400, "device_id는 영문·숫자·-·_ 1~64자")
    for k in ("has_helmet", "has_vest"):
        if not isinstance(r.get(k), bool):
            raise BadRecord(400, f"{k}는 true/false")
    if r["has_helmet"] and r["has_vest"]:
        raise BadRecord(400, "위반이 아님 (안전모·조끼 모두 착용)")

    confidence = r.get("confidence")
    if confidence is not None:
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise BadRecord(400, "confidence는 0~1 숫자 또는 null")

    detected_at = r.get("detected_at")
    if detected_at is None:
        at = datetime.now(timezone.utc)
    else:
        try:
            at = datetime.fromisoformat(detected_at)
        except (TypeError, ValueError):
            raise BadRecord(400, "detected_at은 ISO 8601 시각")
        if at.tzinfo is None:
            raise BadRecord(400, "detected_at에 시간대가 필요함")

    return {
        "created_at": at.astimezone(timezone.utc).isoformat(),
        "device_id": device_id,
        "has_helmet": r["has_helmet"],
        "has_vest": r["has_vest"],
        "confidence": confidence,
    }


def check_image(data: bytes) -> None:
    if len(data) > MAX_IMAGE_BYTES:
        raise BadRecord(413, "사진이 5MB를 넘음")
    if not data.startswith(b"\xff\xd8"):
        raise BadRecord(415, "사진이 JPEG가 아님")


def save_to_buffer(row: dict, image: bytes) -> str:
    """사진을 먼저, 기록(.json)을 나중에 쓴다. .json이 있으면 완전히 저장된 것이다."""
    BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    rid = uuid.uuid4().hex
    date = row["created_at"][:10]
    item = {**row, "path": f"{row['device_id']}/{date}/{rid}.jpg"}
    (BUFFER_DIR / f"{rid}.jpg").write_bytes(image)
    tmp = BUFFER_DIR / f"{rid}.json.tmp"
    tmp.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    tmp.replace(BUFFER_DIR / f"{rid}.json")
    return rid


def buffered_count() -> int:
    return len(list(BUFFER_DIR.glob("*.json"))) if BUFFER_DIR.exists() else 0


@app.get("/health")
def health():
    return {"service": SERVICE, "status": "ok", "buffered": buffered_count()}


@app.post("/records")
async def records(result: str = Form(...), image: UploadFile = File(...)):
    row = parse_result(result)
    data = await image.read()
    check_image(data)
    rid = save_to_buffer(row, data)
    log.info("버퍼 저장 %s (%s)", rid, row["device_id"])
    return JSONResponse({"status": "buffered"}, status_code=202)
