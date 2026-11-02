FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
# worker 1개, access 로그 끔 (main.py의 uvicorn.run)
CMD ["python", "main.py"]
