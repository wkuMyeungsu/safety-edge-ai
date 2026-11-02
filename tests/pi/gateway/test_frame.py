"""POST /frame 입력 검사와 처리 흐름 (docs/contracts/frame.md).

CI에는 모델이 없을 수 있어서 여기서는 판정 결과를 보지 않는다. 실제 판정은 tests/e2e.
"""

import time
import uuid

import pytest
import requests

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


def post(url, body=JPEG, device_id="cam-01"):
    headers = {"Content-Type": "image/jpeg"}
    if device_id is not None:
        headers["X-Device-Id"] = device_id
    return requests.post(f"{url}/frame", data=body, headers=headers, timeout=10)


def wait_recent(url, device_id, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        items = requests.get(f"{url}/recent", params={"device_id": device_id}, timeout=5).json()["items"]
        if items:
            return items[0]
        time.sleep(0.3)
    pytest.fail(f"{timeout}초 안에 처리되지 않음: {device_id}")


def test_jpeg_is_queued(gateway_url):
    r = post(gateway_url)
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "queued"


def test_queued_frame_is_processed(gateway_url, image_bytes):
    device_id = f"test-{uuid.uuid4().hex[:8]}"
    assert post(gateway_url, image_bytes("blank.jpg"), device_id).status_code == 202
    entry = wait_recent(gateway_url, device_id)
    # 모델이 없으면 inference가 503 → error. 있으면 판정 결과
    assert entry["verdict"] in ("pass", "fail", "no_person", "error")
    assert entry["received_at"].endswith("+00:00")


@pytest.mark.parametrize("device_id", [None, "", "../etc", "a" * 65, "cam 01"])
def test_bad_device_id_is_400(gateway_url, device_id):
    assert post(gateway_url, device_id=device_id).status_code == 400


@pytest.mark.parametrize("body", [b"", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, b"hello"])
def test_non_jpeg_is_400(gateway_url, body):
    assert post(gateway_url, body).status_code == 400


def test_large_image_is_413(gateway_url):
    big = b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024)
    assert post(gateway_url, big).status_code == 413


def test_health_shows_queue(gateway_url):
    body = requests.get(f"{gateway_url}/health", timeout=5).json()
    assert body["queue"] >= 0
    assert body["queue_max"] >= 1
    assert isinstance(body["stats"], dict)
