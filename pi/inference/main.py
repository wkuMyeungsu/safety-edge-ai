"""inference: gateway가 보낸 JPEG에서 안전모·조끼 착용을 판정한다 (docs/contracts/inference.md).

- POST /predict  본문 = JPEG 바이트. 판정 JSON을 돌려준다.
- GET  /health   모델이 없어도 200 (model_loaded로 구분). 모델이 필요한 판정은 503.
모델은 서버 시작 때 한 번만 불러온다. uvicorn worker는 1개 (Pi 5 4GB).
"""

import ast
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import uvicorn
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from detector import categorize, decode, judge, preprocess

SERVICE = os.environ.get("SERVICE_NAME", "inference")
PORT = int(os.environ.get("PORT", "8003"))
MODEL_PATH = Path(os.environ.get("MODEL_PATH", "/models/ppe_yolov8.onnx"))
ORT_THREADS = int(os.environ.get("ORT_THREADS", "3"))
CONF_THRES = float(os.environ.get("CONF_THRES", "0.4"))
IOU_THRES = float(os.environ.get("IOU_THRES", "0.45"))
MAX_BYTES = 2 * 1024 * 1024  # 계약: 최대 2MB

log = logging.getLogger("inference")
model = {"session": None, "input": None, "size": None, "classes": [], "categories": {}, "error": None}
run_lock = threading.Lock()  # 한 번에 한 장씩 (Pi CPU를 나눠 쓰지 않게)


def class_names(session: ort.InferenceSession) -> list[str]:
    """ultralytics가 ONNX에 넣어 둔 클래스 이름 ({0: 'Hardhat', ...})을 읽는다."""
    raw = session.get_modelmeta().custom_metadata_map.get("names")
    if not raw:
        return []
    names = ast.literal_eval(raw)
    return [names[i] for i in sorted(names)] if isinstance(names, dict) else list(names)


def load_model() -> None:
    if not MODEL_PATH.is_file():
        model["error"] = f"모델 파일 없음: {MODEL_PATH} (받는 법은 pi/models/README.md)"
        log.warning(model["error"])
        return
    try:
        options = ort.SessionOptions()
        options.intra_op_num_threads = ORT_THREADS
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        session = ort.InferenceSession(str(MODEL_PATH), options, providers=["CPUExecutionProvider"])
        inp = session.get_inputs()[0]
        classes = class_names(session)
        categories = {classes[i]: c for i, c in categorize(classes).items()}
        found = set(categories.values())
        if not ({"helmet", "no_helmet"} & found and {"vest", "no_vest"} & found):
            model["error"] = f"안전모·조끼를 판정할 수 없는 모델: 클래스 {classes}"
            log.error(model["error"])
            return
        model.update(session=session, input=inp.name, size=int(inp.shape[-1]) if isinstance(inp.shape[-1], int) else 640,
                     classes=classes, categories=categories, error=None)
        log.info("모델 불러옴: %s, 입력 %s %s, 판정에 쓰는 클래스 %s", MODEL_PATH.name, inp.name, inp.shape, categories)
    except Exception as e:  # 깨진 파일 등: 서버는 살아 있고 /predict만 503
        model["error"] = f"모델을 불러오지 못함: {e.__class__.__name__}: {e}"
        log.error(model["error"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield


app = FastAPI(title="inference", lifespan=lifespan)


def error(code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"detail": detail})


@app.get("/health")
def health():
    return {
        "service": SERVICE,
        "status": "ok",
        "model_loaded": model["session"] is not None,
        "model": MODEL_PATH.name,
        "classes": model["classes"],
        "error": model["error"],
    }


@app.post("/predict")
async def predict(request: Request):
    # Content-Length가 없는 chunked 요청도 읽는 도중에 제한한다.
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BYTES:
            return error(413, f"사진이 {MAX_BYTES // 1024 // 1024}MB를 넘음")
        body.extend(chunk)
    # 추론은 CPU를 몇백 ms 쓰므로 이벤트 루프 밖(스레드)에서 돌린다. /health가 그동안에도 답하게
    return await run_in_threadpool(handle, bytes(body))


def handle(body: bytes):
    if len(body) > MAX_BYTES:
        return error(413, f"사진이 {MAX_BYTES // 1024 // 1024}MB를 넘음 ({len(body)} bytes)")
    if not body:
        return error(400, "본문이 비었음 (JPEG 바이트를 그대로 보낸다)")
    # imdecode는 PNG 등도 읽으므로 JPEG 시그니처를 먼저 확인한다.
    if not body.startswith(b"\xff\xd8\xff"):
        return error(400, "JPEG로 읽을 수 없음")
    try:
        image = cv2.imdecode(np.frombuffer(body, dtype=np.uint8), cv2.IMREAD_COLOR)
    except cv2.error:
        return error(400, "JPEG로 읽을 수 없음")
    if image is None:
        return error(400, "JPEG로 읽을 수 없음")
    if model["session"] is None:
        return error(503, model["error"] or "모델이 없음")
    started = time.perf_counter()
    height, width = image.shape[:2]
    blob, r, left, top = preprocess(image, model["size"])
    with run_lock:
        output = model["session"].run(None, {model["input"]: blob})[0]
    detections = decode(output, model["classes"], r, left, top, width, height, CONF_THRES, IOU_THRES)
    result = judge(detections, model["categories"])
    result.update(detections=detections, image={"width": width, "height": height}, model=MODEL_PATH.name,
                  infer_ms=round((time.perf_counter() - started) * 1000))
    log.info("판정 %s (helmet=%s vest=%s, 사람 %d, %dms)", result["verdict"], result["has_helmet"], result["has_vest"],
             result["persons"], result["infer_ms"])
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=PORT, workers=1, log_level="info")
