"""uploader: gateway가 넘긴 위반 판정 + 사진을 Supabase에 저장한다.

계약: docs/contracts/record-storage.md, docs/contracts/storage.md
"""

import os

from fastapi import FastAPI

SERVICE = os.environ.get("SERVICE_NAME", "uploader")

app = FastAPI()


@app.get("/health")
def health():
    return {"service": SERVICE, "status": "ok"}
