"""uploader: gateway가 넘긴 위반 판정 + 사진을 Supabase에 저장한다.

계약: docs/contracts/record-storage.md, docs/contracts/storage.md
받은 기록은 먼저 BUFFER_DIR에 파일로 남긴다 (사진 {id}.jpg, 기록 {id}.json).
그다음 Supabase로 보내고, 성공하면 버퍼에서 지운다. 실패하면 RETRY_INTERVAL초마다 다시 보낸다.
Supabase가 거절한 기록(4xx)은 다시 보내도 안 되므로 BUFFER_DIR/failed/로 옮긴다.
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

SERVICE = os.environ.get("SERVICE_NAME", "uploader")
PORT = int(os.environ.get("PORT", "8004"))
BUFFER_DIR = Path(os.environ.get("BUFFER_DIR", "/buffer"))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
RETRY_INTERVAL = float(os.environ.get("RETRY_INTERVAL", "30"))

BUCKET = "violations"
TABLE = "safety_logs"
SEND_TIMEOUT = 10  # 계약: Supabase 응답을 10초 넘게 기다리지 않는다
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # violations 버킷 제한과 같다
DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# 팀 로그 형식 (로그 설계 3절). 세 서비스가 같은 줄을 쓴다
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)-8s %(name)s %(filename)s:%(lineno)d %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("pi.uploader")
retry_log = logging.getLogger("pi.uploader.retry")

# 요청 처리와 재시도 작업이 같은 기록을 동시에 보내지 않게 한다
send_lock = asyncio.Lock()


class Rejected(Exception):
    """Supabase가 4xx로 거절함. 다시 보내도 같은 결과다."""

    def __init__(self, what: str, code: int, detail: str):
        super().__init__(f"{what} {code}: {detail}")
        self.code = code
        self.detail = f"{what}: {detail}"


def configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def auth_headers() -> dict:
    headers = {"apikey": SUPABASE_KEY}
    if SUPABASE_KEY.startswith("eyJ"):  # 예전 형식(JWT) service_role 키는 Authorization도 필요
        headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
    return headers


def check_response(r: httpx.Response, what: str) -> None:
    if r.is_success:
        return
    if 400 <= r.status_code < 500 and r.status_code not in (408, 429):
        raise Rejected(what, r.status_code, r.text[:200])
    r.raise_for_status()


async def send(client: httpx.AsyncClient, rid: str, item: dict) -> int:
    """버퍼의 기록 하나를 Supabase에 올리고 safety_logs.id를 돌려준다."""
    image = (BUFFER_DIR / f"{rid}.jpg").read_bytes()
    item = dict(item)
    path = item.pop("path")
    item.pop("frame", None)  # 로그용. safety_logs 컬럼이 아니다

    # 같은 경로로 덮어쓰기(x-upsert)라서 재시도해도 사진이 두 장 생기지 않는다
    r = await client.post(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}",
        content=image,
        headers={**auth_headers(), "Content-Type": "image/jpeg", "x-upsert": "true"},
    )
    check_response(r, "사진 업로드")

    row = {**item, "image_url": f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"}
    r = await client.post(
        f"{SUPABASE_URL}/rest/v1/{TABLE}",
        json=row,
        headers={**auth_headers(), "Prefer": "return=representation"},
    )
    check_response(r, "기록 저장")
    new_id = r.json()[0]["id"]

    (BUFFER_DIR / f"{rid}.json").unlink()
    (BUFFER_DIR / f"{rid}.jpg").unlink()
    return new_id


def move_to_failed(rid: str) -> None:
    failed = BUFFER_DIR / "failed"
    failed.mkdir(exist_ok=True)
    for ext in ("json", "jpg"):
        src = BUFFER_DIR / f"{rid}.{ext}"
        if src.exists():
            src.replace(failed / src.name)


async def try_send(client: httpx.AsyncClient, rid: str) -> tuple[int | None, str | None]:
    """(safety_logs.id, None)이면 저장됨, (None, 오류 이름)이면 연결 문제로 버퍼에 남음.
    (None, None)이면 이미 보냈거나 거절돼 failed/로 옮김. 연결 실패 로그는 부르는 쪽이 남긴다."""
    async with send_lock:
        record = BUFFER_DIR / f"{rid}.json"
        if not record.exists():  # 다른 쪽에서 이미 보냄
            return None, None
        item = json.loads(record.read_text(encoding="utf-8"))
        started = time.perf_counter()
        try:
            log_id = await asyncio.wait_for(send(client, rid, item), SEND_TIMEOUT)
        except Rejected as e:
            log.error("Supabase가 거절, failed/로 옮김 frame=%s rid=%s code=%d detail=%s",
                      item.get("frame"), rid, e.code, e.detail)
            move_to_failed(rid)
            return None, None
        except (httpx.HTTPError, asyncio.TimeoutError, OSError) as e:
            return None, type(e).__name__
        log.info("저장 성공 frame=%s rid=%s log_id=%s device=%s send_ms=%d", item.get("frame"), rid, log_id,
                 item["device_id"], (time.perf_counter() - started) * 1000)
        return log_id, None


async def retry_loop(client: httpx.AsyncClient) -> None:
    while True:
        await asyncio.sleep(RETRY_INTERVAL)
        if not BUFFER_DIR.exists():
            continue
        tried = sent = 0
        error = None
        for p in sorted(BUFFER_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime):
            tried += 1
            log_id, error = await try_send(client, p.stem)
            sent += log_id is not None
            if error:
                break  # 아직 연결이 안 되면 다음 주기에 다시
        # rid마다 찍지 않고 한 바퀴에 한 줄 (끊겨 있으면 30초마다 같은 줄이 쌓이지 않게)
        if error:
            retry_log.warning("재전송 실패, 다음에 다시 tried=%d sent=%d pending=%d error=%s",
                              tried, sent, buffered_count(), error)
        elif sent:
            retry_log.info("재전송 sent=%d pending=%d", sent, buffered_count())


@asynccontextmanager
async def lifespan(app: FastAPI):
    failed = len(list((BUFFER_DIR / "failed").glob("*.json"))) if (BUFFER_DIR / "failed").exists() else 0
    log.info("시작 commit=%s supabase=%s pending=%d failed=%d retry_s=%g",
             os.environ.get("COMMIT") or "unknown", configured(), buffered_count(), failed, RETRY_INTERVAL)
    if not configured():
        log.warning("SUPABASE_URL·SUPABASE_SERVICE_KEY 없음: 받은 기록은 버퍼에만 쌓는다")
        app.state.client = None
        yield
        return
    async with httpx.AsyncClient(timeout=SEND_TIMEOUT) as client:
        app.state.client = client
        task = asyncio.create_task(retry_loop(client))
        yield
        task.cancel()


app = FastAPI(lifespan=lifespan)


class BadRecord(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


@app.exception_handler(BadRecord)
async def bad_record(_: Request, e: BadRecord):
    log.warning("요청 거부 code=%d detail=%s", e.status, e.detail)
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

    # gateway가 붙인 사진 번호 (선택). 로그에만 쓰고 safety_logs에는 넣지 않는다. 형식이 틀리면 버린다
    frame = r.get("frame_id")
    if not isinstance(frame, str) or not DEVICE_ID.match(frame):
        frame = None

    return {
        "created_at": at.astimezone(timezone.utc).isoformat(),
        "device_id": device_id,
        "has_helmet": r["has_helmet"],
        "has_vest": r["has_vest"],
        "confidence": confidence,
        "frame": frame,
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
    log.debug("버퍼에 저장 frame=%s rid=%s path=%s bytes=%d", row["frame"], rid, item["path"], len(image))
    return rid


def buffered_count() -> int:
    return len(list(BUFFER_DIR.glob("*.json"))) if BUFFER_DIR.exists() else 0


@app.get("/health")
def health():
    return {"service": SERVICE, "status": "ok", "supabase": configured(), "buffered": buffered_count()}


@app.post("/records")
async def records(request: Request, result: str = Form(...), image: UploadFile = File(...)):
    row = parse_result(result)
    data = await image.read()
    check_image(data)
    rid = save_to_buffer(row, data)

    client = request.app.state.client
    # 재시도 작업이 보내는 중이면 기다리지 않는다. 기다리면 gateway 제한 시간(15초)을 넘을 수 있다.
    # 이 기록은 버퍼에 있으니 다음 재시도 때 올라간다.
    frame, device = row["frame"], row["device_id"]
    if client is None:
        log.info("버퍼에 둠 frame=%s rid=%s device=%s reason=supabase_설정_없음", frame, rid, device)
    elif send_lock.locked():
        log.info("버퍼에 둠 frame=%s rid=%s device=%s reason=재전송_중", frame, rid, device)
    else:
        log_id, error = await try_send(client, rid)
        if log_id is not None:
            return JSONResponse({"status": "stored", "id": log_id}, status_code=201)
        if error:
            log.warning("전송 실패, 버퍼에 둠 frame=%s rid=%s device=%s error=%s", frame, rid, device, error)
    return JSONResponse({"status": "buffered"}, status_code=202)


if __name__ == "__main__":
    # access 로그는 끈다 (healthcheck가 15초마다 찍힌다). 기동 메시지도 위 형식으로 찍힌다
    uvicorn.run(app, host="0.0.0.0", port=PORT, workers=1, log_config=None, access_log=False)
