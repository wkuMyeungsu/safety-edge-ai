"""모든 테스트가 같이 쓰는 fixture.

서비스 주소는 환경변수로 바꿀 수 있다. 기본값은 CI와 PC에서
`docker compose -f pi/docker-compose.yml -f pi/docker-compose.ci.yml up` 했을 때의 주소다.
"""

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
MODEL_PATH = ROOT / "pi" / "models" / "ppe_yolov8.onnx"


@pytest.fixture(scope="session")
def gateway_url() -> str:
    return os.environ.get("GATEWAY_URL", "http://localhost:8001")


@pytest.fixture(scope="session")
def inference_url() -> str:
    return os.environ.get("INFERENCE_URL", "http://localhost:8003")


@pytest.fixture(scope="session")
def uploader_url() -> str:
    return os.environ.get("UPLOADER_URL", "http://localhost:8004")


@pytest.fixture(scope="session")
def image_bytes():
    """tests/fixtures/images/ 의 사진을 이름으로 읽는다. 예: image_bytes("no_helmet.jpg")"""

    def load(name: str) -> bytes:
        return (FIXTURES / "images" / name).read_bytes()

    return load


def pytest_collection_modifyitems(config, items):
    if MODEL_PATH.exists():
        return
    skip = pytest.mark.skip(reason=f"모델 파일 없음: {MODEL_PATH.relative_to(ROOT)}")
    for item in items:
        if "model" in item.keywords:
            item.add_marker(skip)
