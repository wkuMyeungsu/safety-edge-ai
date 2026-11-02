"""inference: gateway가 보낸 JPEG에서 안전모·조끼 착용을 판정한다 (docs/contracts/inference.md).

- POST /predict  본문 = JPEG 바이트. 판정 JSON을 돌려준다.
- GET  /health   모델이 없어도 200 (model_loaded로 구분). 모델이 필요한 판정은 503.
모델은 서버 시작 때 한 번만 불러온다. uvicorn worker는 1개 (Pi 5 4GB).
"""

import ast
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

SERVICE = os.environ.get("SERVICE_NAME", "inference")
PORT = int(os.environ.get("PORT", "8003"))
MODEL_PATH = Path(os.environ.get("MODEL_PATH", "/models/ppe_yolov8.onnx"))
ORT_THREADS = int(os.environ.get("ORT_THREADS", "3"))
MAX_BYTES = 2 * 1024 * 1024  # 계약: 최대 2MB

log = logging.getLogger("inference")
model = {"session": None, "input": None, "size": None, "classes": [], "error": None}


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
        model.update(session=session, input=inp.name, size=int(inp.shape[-1]) if isinstance(inp.shape[-1], int) else 640,
                     classes=class_names(session), error=None)
        log.info("모델 불러옴: %s, 입력 %s %s, 클래스 %s", MODEL_PATH.name, inp.name, inp.shape, model["classes"])
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
    body = await request.body()
    if len(body) > MAX_BYTES:
        return error(413, f"사진이 {MAX_BYTES // 1024 // 1024}MB를 넘음 ({len(body)} bytes)")
    if not body:
        return error(400, "본문이 비었음 (JPEG 바이트를 그대로 보낸다)")
    image = cv2.imdecode(np.frombuffer(body, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return error(400, "JPEG로 읽을 수 없음")
    if model["session"] is None:
        return error(503, model["error"] or "모델이 없음")
    return error(501, "판정은 아직 구현 전")  # 다음 PR에서 YOLOv8 결과 해석과 판정을 넣는다


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=PORT, workers=1, log_level="info")
