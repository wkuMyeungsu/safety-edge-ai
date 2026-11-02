FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && python -c "import cv2, numpy, onnxruntime; print('cv2', cv2.__version__, 'onnxruntime', onnxruntime.__version__)"
COPY *.py ./
# uvicorn worker 1개 (모델을 한 번만 불러온다). 포트는 compose의 PORT(8003)
CMD ["python", "main.py"]
