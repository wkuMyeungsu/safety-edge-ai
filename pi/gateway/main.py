"""gateway: ESP32가 보낸 사진을 받아 inference → (위반이면) uploader 순서로 넘긴다.

계약: docs/contracts/frame.md (esp32 → gateway), inference.md, record-storage.md
- POST /frame    본문 = JPEG 바이트, 헤더 X-Device-Id. 대기 줄에 넣고 바로 202를 돌려준다.
- GET  /health   상태, 대기 줄 길이, 처리 건수
- GET  /recent   최근 처리 결과 (디버깅·테스트용)
처리 작업자는 1개다. inference가 한 번에 한 장씩 처리하기 때문이다.
대기 줄이 가득 차면 새 사진은 503으로 거절한다 (ESP32는 버리고 다음 사진을 보낸다).
"""

import asyncio
import json
import logging
import os
import re
import time
from collections import Counter, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

SERVICE = os.environ.get("SERVICE_NAME", "gateway")
PORT = int(os.environ.get("PORT", "8001"))
INFERENCE_URL = os.environ.get("INFERENCE_URL", "http://inference:8003").rstrip("/")
UPLOADER_URL = os.environ.get("UPLOADER_URL", "http://uploader:8004").rstrip("/")
QUEUE_MAX = int(os.environ.get("QUEUE_MAX", "4"))
INFERENCE_TIMEOUT = float(os.environ.get("INFERENCE_TIMEOUT", "10"))
UPLOADER_TIMEOUT = float(os.environ.get("UPLOADER_TIMEOUT", "15"))  # uploader는 Supabase를 최대 10초 기다린다
RECENT_MAX = 50

MAX_BYTES = 2 * 1024 * 1024  # inference 제한과 같다
DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # uploader 검사와 같다

logging.basicConfig(level=logging.INFO, format="%(asctime)s gateway %(levelname)s %(message)s")
log = logging.getLogger("gateway")
logging.getLogger("httpx").setLevel(logging.WARNING)  # 요청마다 찍히는 로그는 끈다


@dataclass
class Frame:
    device_id: str
    image: bytes
    received_at: datetime
    queued: float  # time.monotonic()


queue: asyncio.Queue[Frame] = asyncio.Queue(maxsize=QUEUE_MAX)
stats: Counter = Counter()
recent: deque = deque(maxlen=RECENT_MAX)


def error(code: int, detail: str, status: str = "rejected") -> JSONResponse:
    stats["rejected" if code != 503 else "busy"] += 1
    log.warning("거부 %d: %s", code, detail)
    return JSONResponse({"status": status, "detail": detail}, status_code=code)


async def call_inference(client: httpx.AsyncClient, frame: Frame) -> dict | None:
    """판정 JSON, 실패하면 None (계약상 inference 오류는 버리고 로그만 남긴다)."""
    try:
        r = await client.post(f"{INFERENCE_URL}/predict", content=frame.image,
                              headers={"Content-Type": "image/jpeg"}, timeout=INFERENCE_TIMEOUT)
    except httpx.HTTPError as e:
        log.error("inference 호출 실패 (%s): %r", frame.device_id, e)
        return None
    if r.status_code != 200:
        log.error("inference %d (%s): %s", r.status_code, frame.device_id, r.text[:200])
        return None
    return r.json()


async def call_uploader(client: httpx.AsyncClient, frame: Frame, result: dict) -> str:
    """'stored' · 'buffered' · 'error'."""
    record = {**result, "device_id": frame.device_id, "detected_at": frame.received_at.isoformat()}
    record.pop("detections", None)  # uploader는 쓰지 않는다
    try:
        r = await client.post(
            f"{UPLOADER_URL}/records",
            data={"result": json.dumps(record, ensure_ascii=False)},
            files={"image": ("frame.jpg", frame.image, "image/jpeg")},
            timeout=UPLOADER_TIMEOUT,
        )
    except httpx.HTTPError as e:
        log.error("uploader 호출 실패 (%s): %r", frame.device_id, e)
        return "error"
    if r.status_code in (201, 202):
        return r.json().get("status", "stored" if r.status_code == 201 else "buffered")
    log.error("uploader %d (%s): %s", r.status_code, frame.device_id, r.text[:200])
    return "error"


async def process(client: httpx.AsyncClient, frame: Frame) -> dict:
    started = time.monotonic()
    entry = {
        "device_id": frame.device_id,
        "received_at": frame.received_at.isoformat(),
        "wait_ms": round((started - frame.queued) * 1000),
        "verdict": None,
        "upload": None,
    }
    result = await call_inference(client, frame)
    if result is None:
        entry["verdict"] = "error"
    else:
        entry.update(verdict=result.get("verdict"), has_helmet=result.get("has_helmet"),
                     has_vest=result.get("has_vest"), confidence=result.get("confidence"),
                     infer_ms=result.get("infer_ms"))
        if entry["verdict"] == "fail":
            entry["upload"] = await call_uploader(client, frame, result)
            stats[f"upload_{entry['upload']}"] += 1
    stats[f"verdict_{entry['verdict']}"] += 1
    entry["total_ms"] = round((time.monotonic() - frame.queued) * 1000)
    log.info("%s %s helmet=%s vest=%s upload=%s 대기 %dms 전체 %dms", frame.device_id, entry["verdict"],
             entry.get("has_helmet"), entry.get("has_vest"), entry["upload"], entry["wait_ms"], entry["total_ms"])
    return entry


async def worker(client: httpx.AsyncClient) -> None:
    while True:
        frame = await queue.get()
        try:
            recent.append(await process(client, frame))
        except Exception:  # 한 장 때문에 작업자가 멈추지 않게
            log.exception("처리 중 예외 (%s)", frame.device_id)
            stats["verdict_error"] += 1
        finally:
            queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient() as client:
        task = asyncio.create_task(worker(client))
        log.info("시작: inference=%s uploader=%s 대기 줄 %d", INFERENCE_URL, UPLOADER_URL, QUEUE_MAX)
        yield
        task.cancel()


app = FastAPI(title="gateway", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"service": SERVICE, "status": "ok", "queue": queue.qsize(), "queue_max": QUEUE_MAX, "stats": dict(stats)}


@app.get("/recent")
async def get_recent(device_id: str | None = None):
    items = [e for e in recent if device_id is None or e["device_id"] == device_id]
    return {"items": items[::-1]}  # 최근 것부터


@app.post("/frame")
async def frame(request: Request):
    device_id = request.headers.get("x-device-id", "")
    if not DEVICE_ID.match(device_id):
        return error(400, "X-Device-Id 헤더는 영문·숫자·-·_ 1~64자")

    body = bytearray()
    async for chunk in request.stream():  # Content-Length 없는 chunked 요청도 읽는 도중에 제한
        if len(body) + len(chunk) > MAX_BYTES:
            return error(413, f"사진이 {MAX_BYTES // 1024 // 1024}MB를 넘음")
        body.extend(chunk)
    if not body.startswith(b"\xff\xd8\xff"):
        return error(400, "본문이 JPEG가 아님 (JPEG 바이트를 그대로 보낸다)")

    item = Frame(device_id, bytes(body), datetime.now(timezone.utc), time.monotonic())
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        return error(503, "대기 줄이 가득 참. 이 사진은 버린다", status="busy")
    stats["received"] += 1
    return JSONResponse({"status": "queued", "queue": queue.qsize()}, status_code=202)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, workers=1, log_level="warning")
