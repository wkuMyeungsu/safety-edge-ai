"""gateway → inference → uploader 전체 흐름. 실제 모델이 있어야 의미가 있다.

CI에는 Supabase 값이 없어서 위반 기록은 uploader 버퍼에 쌓이고 upload는 "buffered"가 된다.
"""

import json
import time
import uuid
from pathlib import Path

import pytest
import requests

IMAGES = Path(__file__).resolve().parent.parent / "pi" / "inference" / "images"
EXPECTED = json.loads((IMAGES.parent / "expected.json").read_text(encoding="utf-8"))


def send_and_wait(gateway_url, image: bytes, timeout=60):
    device_id = f"e2e-{uuid.uuid4().hex[:8]}"
    r = requests.post(f"{gateway_url}/frame", data=image, timeout=10,
                      headers={"Content-Type": "image/jpeg", "X-Device-Id": device_id})
    assert r.status_code == 202, r.text
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        items = requests.get(f"{gateway_url}/recent", params={"device_id": device_id}, timeout=5).json()["items"]
        if items:
            return items[0]
        time.sleep(0.5)
    pytest.fail(f"{timeout}초 안에 처리되지 않음")


@pytest.mark.model
@pytest.mark.parametrize("name", ["test_0.jpg", "test_26.jpg"])
def test_violation_goes_to_uploader(gateway_url, name):
    entry = send_and_wait(gateway_url, (IMAGES / name).read_bytes())
    want = EXPECTED[name]
    assert entry["verdict"] == "fail"
    assert entry["has_helmet"] == want["has_helmet"]
    assert entry["has_vest"] == want["has_vest"]
    assert entry["upload"] in ("stored", "buffered")


@pytest.mark.model
def test_pass_is_not_uploaded(gateway_url):
    entry = send_and_wait(gateway_url, (IMAGES / "test_11.jpg").read_bytes())
    assert entry["verdict"] == "pass"
    assert entry["upload"] is None
