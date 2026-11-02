"""POST /predict의 응답이 계약(docs/contracts/inference.md)대로인지, 사진별 판정이 기대대로인지. 실제 모델이 필요하다."""

import json
from pathlib import Path

import jsonschema
import pytest
import requests

HERE = Path(__file__).parent
EXPECTED = {k: v for k, v in json.loads((HERE / "expected.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}

# docs/contracts/inference.md "응답 200"
RESPONSE = {
    "type": "object",
    "required": ["verdict", "has_helmet", "has_vest", "confidence", "persons", "detections", "image", "model", "infer_ms"],
    "properties": {
        "verdict": {"enum": ["pass", "fail", "no_person"]},
        "has_helmet": {"type": "boolean"},
        "has_vest": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "persons": {"type": "integer", "minimum": 0},
        "detections": {"type": "array", "items": {
            "type": "object", "required": ["label", "score", "box"],
            "properties": {"label": {"type": "string"}, "score": {"type": "number", "minimum": 0, "maximum": 1},
                           "box": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}}}},
        "image": {"type": "object", "required": ["width", "height"]},
        "model": {"type": "string"},
        "infer_ms": {"type": "integer", "minimum": 0},
    },
}


def predict(url, photo: bytes):
    return requests.post(f"{url}/predict", data=photo, headers={"Content-Type": "image/jpeg"}, timeout=30)


@pytest.fixture
def sample_bytes(image_bytes):
    def load(name):
        local = HERE / "images" / name
        return local.read_bytes() if local.is_file() else image_bytes(name)
    return load


@pytest.mark.model
@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_response_follows_contract(inference_url, sample_bytes, name):
    r = predict(inference_url, sample_bytes(name))
    assert r.status_code == 200, r.text
    body = r.json()
    jsonschema.validate(body, RESPONSE)
    # 판정 규칙: pass는 둘 다 착용, fail은 하나라도 미착용, no_person은 사람 0명
    if body["verdict"] == "pass":
        assert body["has_helmet"] and body["has_vest"]
    elif body["verdict"] == "fail":
        assert not (body["has_helmet"] and body["has_vest"]) and body["persons"] > 0
    else:
        assert body["persons"] == 0
    w, h = body["image"]["width"], body["image"]["height"]
    for d in body["detections"]:
        x1, y1, x2, y2 = d["box"]
        assert 0 <= x1 <= x2 <= w and 0 <= y1 <= y2 <= h, f"상자가 사진 밖: {d}"


@pytest.mark.model
@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_expected_verdict(inference_url, sample_bytes, name):
    r = predict(inference_url, sample_bytes(name))
    assert r.status_code == 200, r.text
    body = r.json()
    for field, want in EXPECTED[name].items():
        assert body[field] == want, f"{name}: {field}={body[field]!r}, 기대 {want!r} (검출: {body['detections']})"
