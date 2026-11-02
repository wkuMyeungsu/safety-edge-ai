"""POST /records 입력 검사 (docs/contracts/record-storage.md).

CI에는 Supabase 값(.env)이 없어서 정상 요청은 버퍼에 쌓이고 202가 된다.
"""

import json

import pytest
import requests

# JPEG 시작 표식(FF D8)만 있으면 uploader는 JPEG로 받는다
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"
FAIL = {"device_id": "esp32-01", "has_helmet": False, "has_vest": True, "confidence": 0.82}


def post(url, result, image=JPEG, content_type="image/jpeg"):
    files = {"image": ("frame.jpg", image, content_type)}
    data = {"result": result if isinstance(result, str) else json.dumps(result)}
    return requests.post(f"{url}/records", data=data, files=files, timeout=15)


def test_fail_result_is_accepted(uploader_url):
    r = post(uploader_url, FAIL)
    assert r.status_code in (201, 202), r.text
    assert r.json()["status"] in ("stored", "buffered")


def test_inference_response_fields_are_ignored(uploader_url):
    # gateway는 inference 응답에 device_id만 더해 넘긴다 (inference.md)
    result = {**FAIL, "verdict": "fail", "persons": 1, "detections": [], "infer_ms": 120}
    r = post(uploader_url, result)
    assert r.status_code in (201, 202), r.text


@pytest.mark.parametrize("frame_id", ["ab12cd34", "bad frame\nid", 123])
def test_frame_id_is_optional_and_never_rejected(uploader_url, frame_id):
    # frame_id는 로그용 선택 필드. 형식이 틀려도 기록은 받는다 (로그 설계 5절)
    r = post(uploader_url, {**FAIL, "frame_id": frame_id})
    assert r.status_code in (201, 202), r.text


def test_detected_at_is_accepted(uploader_url):
    r = post(uploader_url, {**FAIL, "detected_at": "2026-11-02T09:30:00+09:00"})
    assert r.status_code in (201, 202), r.text


@pytest.mark.parametrize(
    "result",
    [
        "not json",
        {**FAIL, "has_helmet": True, "has_vest": True},  # pass는 저장하지 않는다
        {k: v for k, v in FAIL.items() if k != "device_id"},
        {**FAIL, "device_id": "../etc"},
        {**FAIL, "has_vest": "yes"},
        {**FAIL, "confidence": 1.5},
        {**FAIL, "detected_at": "2026-11-02T09:30:00"},  # 시간대 없음
    ],
)
def test_bad_result_is_400(uploader_url, result):
    assert post(uploader_url, result).status_code == 400


def test_missing_image_is_400(uploader_url):
    r = requests.post(f"{uploader_url}/records", data={"result": json.dumps(FAIL)}, timeout=15)
    assert r.status_code == 400


def test_non_jpeg_is_415(uploader_url):
    assert post(uploader_url, FAIL, image=b"\x89PNG\r\n\x1a\n", content_type="image/png").status_code == 415


def test_large_image_is_413(uploader_url):
    big = b"\xff\xd8" + b"\x00" * (5 * 1024 * 1024)
    assert post(uploader_url, FAIL, image=big).status_code == 413
