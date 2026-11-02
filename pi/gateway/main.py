"""gateway: ESP32가 보낸 사진을 받아 inference → (위반이면) uploader 순서로 넘긴다.

계약: docs/contracts/frame.md (esp32 → gateway), inference.md, record-storage.md
- POST /frame    본문 = JPEG 바이트, 헤더 X-Device-Id. 대기 줄에 넣고 바로 202를 돌려준다.
                 202 본문의 frame(사진 번호)이 inference·uploader 로그까지 이어진다.
- GET  /health   상태, 대기 줄 길이, 처리 건수
- GET  /recent   최근 처리 결과 (디버깅·테스트용)
처리 작업자는 1개다. inference가 한 번에 한 장씩 처리하기 때문이다.
대기 줄이 가득 차면 새 사진은 503으로 거절한다 (ESP32는 버리고 다음 사진을 보낸다).
인터넷(Tailscale Funnel 등 프록시)을 거쳐 온 요청은 X-Device-Token이 GATEWAY_TOKEN과 같아야 받는다.
같은 네트워크에서 바로 온 요청은 토큰 없이 받는다.
"""

import asyncio
import hmac
import json
import logging
import os
import re
import time
import uuid
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
GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "")
# 프록시(Tailscale Funnel, Cloudflare 등)가 붙이는 헤더. 하나라도 있으면 인터넷을 거쳐 온 요청으로 본다
PROXY_HEADERS = ("x-forwarded-for", "forwarded", "cf-connecting-ip", "tailscale-funnel-request")

MAX_BYTES = 2 * 1024 * 1024  # inference 제한과 같다
DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # uploader 검사와 같다

# 팀 로그 형식 (로그 설계 3절). 세 서비스가 같은 줄을 쓴다
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)-8s %(name)s %(filename)s:%(lineno)d %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # 요청마다 찍히는 로그는 끈다
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("pi.gateway")


@dataclass
class Frame:
    frame_id: str  # 사진 번호, 8자리 hex. 로그로 한 장을 끝까지 따라가는 데 쓴다
    device_id: str
    image: bytes
    received_at: datetime
    queued: float  # time.monotonic()
    person_score: float | None = None  # ESP32 사람 감지 점수 (X-Person-Score, 선택)
    person_count: int | None = None  # ESP32가 찾은 사람 수 (X-Person-Count, 선택)


queue: asyncio.Queue[Frame] = asyncio.Queue(maxsize=QUEUE_MAX)
stats: Counter = Counter()
recent: deque = deque(maxlen=RECENT_MAX)


def error(code: int, detail: str, status: str = "rejected") -> JSONResponse:
    stats[{401: "unauthorized", 503: "busy"}.get(code, "rejected")] += 1
    log.warning("거부 code=%d detail=%s", code, detail)
    return JSONResponse({"status": status, "detail": detail}, status_code=code)


async def call_inference(client: httpx.AsyncClient, frame: Frame) -> dict | None:
    """판정 JSON, 실패하면 None (계약상 inference 오류는 버리고 로그만 남긴다)."""
    try:
        r = await client.post(f"{INFERENCE_URL}/predict", content=frame.image,
                              headers={"Content-Type": "image/jpeg", "X-Frame-Id": frame.frame_id},
                              timeout=INFERENCE_TIMEOUT)
    except httpx.HTTPError as e:
        log.error("inference 호출 실패 frame=%s device=%s error=%r", frame.frame_id, frame.device_id, e)
        return None
    if r.status_code != 200:
        log.error("inference 응답 오류 frame=%s device=%s code=%d detail=%s",
                  frame.frame_id, frame.device_id, r.status_code, r.text[:200])
        return None
    return r.json()


async def call_uploader(client: httpx.AsyncClient, frame: Frame, result: dict) -> str:
    """'stored' · 'buffered' · 'error'."""
    record = {**result, "device_id": frame.device_id, "detected_at": frame.received_at.isoformat(),
              "frame_id": frame.frame_id}
    record.pop("detections", None)  # uploader는 쓰지 않는다
    try:
        r = await client.post(
            f"{UPLOADER_URL}/records",
            data={"result": json.dumps(record, ensure_ascii=False)},
            files={"image": ("frame.jpg", frame.image, "image/jpeg")},
            timeout=UPLOADER_TIMEOUT,
        )
    except httpx.HTTPError as e:
        log.error("uploader 호출 실패 frame=%s device=%s error=%r", frame.frame_id, frame.device_id, e)
        return "error"
    if r.status_code in (201, 202):
        return r.json().get("status", "stored" if r.status_code == 201 else "buffered")
    log.error("uploader 응답 오류 frame=%s device=%s code=%d detail=%s",
              frame.frame_id, frame.device_id, r.status_code, r.text[:200])
    return "error"


def lower(value):
    """로그의 true·false를 소문자로 (로그 설계 3-4). None은 그대로."""
    return str(value).lower() if isinstance(value, bool) else value


async def process(client: httpx.AsyncClient, frame: Frame) -> dict:
    started = time.monotonic()
    entry = {
        "frame": frame.frame_id,
        "device_id": frame.device_id,
        "received_at": frame.received_at.isoformat(),
        "wait_ms": round((started - frame.queued) * 1000),
        "person_score": frame.person_score,
        "person_count": frame.person_count,
        "verdict": None,
        "upload": None,
    }
    result = await call_inference(client, frame)
    if result is None:
        entry["verdict"] = "error"
    else:
        entry.update(verdict=result.get("verdict"), has_helmet=result.get("has_helmet"),
                     has_vest=result.get("has_vest"), confidence=result.get("confidence"), persons=result.get("persons"),
                     infer_ms=result.get("infer_ms"))
        if entry["verdict"] == "fail":
            sent = time.monotonic()
            entry["upload"] = await call_uploader(client, frame, result)
            entry["upload_ms"] = round((time.monotonic() - sent) * 1000)
            stats[f"upload_{entry['upload']}"] += 1
    stats[f"verdict_{entry['verdict']}"] += 1
    entry["total_ms"] = round((time.monotonic() - frame.queued) * 1000)
    log.info("처리 끝 frame=%s device=%s verdict=%s helmet=%s vest=%s persons=%s upload=%s "
             "wait_ms=%d infer_ms=%s upload_ms=%s total_ms=%d esp_score=%s esp_persons=%s",
             frame.frame_id, frame.device_id, entry["verdict"], lower(entry.get("has_helmet")),
             lower(entry.get("has_vest")), entry.get("persons"), entry["upload"], entry["wait_ms"],
             entry.get("infer_ms"), entry.get("upload_ms"), entry["total_ms"], frame.person_score, frame.person_count)
    return entry


async def worker(client: httpx.AsyncClient) -> None:
    while True:
        frame = await queue.get()
        try:
            recent.append(await process(client, frame))
        except Exception:  # 한 장 때문에 작업자가 멈추지 않게
            log.exception("처리 중 예외 frame=%s device=%s", frame.frame_id, frame.device_id)
            stats["verdict_error"] += 1
        finally:
            queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient() as client:
        task = asyncio.create_task(worker(client))
        log.info("시작 commit=%s inference=%s uploader=%s queue_max=%d token=%s", os.environ.get("COMMIT") or "unknown",
                 INFERENCE_URL, UPLOADER_URL, QUEUE_MAX, "설정됨" if GATEWAY_TOKEN else "없음")
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


def number(value: str | None, kind):
    """선택 헤더 값. 없거나 숫자가 아니면 None (잘못된 값 때문에 사진을 버리지 않는다)."""
    try:
        return kind(value) if value is not None else None
    except ValueError:
        return None


@app.post("/frame")
async def frame(request: Request):
    if any(h in request.headers for h in PROXY_HEADERS):
        if not GATEWAY_TOKEN:
            return error(401, "GATEWAY_TOKEN이 설정되지 않아 인터넷을 거친 요청은 받지 않음")
        if not hmac.compare_digest(request.headers.get("x-device-token", "").encode(), GATEWAY_TOKEN.encode()):
            return error(401, "X-Device-Token이 없거나 틀림")

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

    item = Frame(uuid.uuid4().hex[:8], device_id, bytes(body), datetime.now(timezone.utc), time.monotonic(),
                 number(request.headers.get("x-person-score"), float), number(request.headers.get("x-person-count"), int))
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        return error(503, "대기 줄이 가득 참. 이 사진은 버린다", status="busy")
    stats["received"] += 1
    return JSONResponse({"status": "queued", "queue": queue.qsize(), "frame": item.frame_id}, status_code=202)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, workers=1, log_config=None, access_log=False)
