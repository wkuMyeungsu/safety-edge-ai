import requests


def test_health(inference_url):
    r = requests.get(f"{inference_url}/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["service"] == "inference"


def test_health_reports_model(inference_url):
    """모델이 없어도 200이고, 모델 상태를 알려 준다 (docs/contracts/inference.md '상태 확인')."""
    body = requests.get(f"{inference_url}/health", timeout=5).json()
    assert isinstance(body["model_loaded"], bool)
    assert body["model"].endswith(".onnx")
    assert isinstance(body["classes"], list)
    if body["model_loaded"]:
        assert body["classes"], "모델은 불러왔는데 클래스 이름이 없음 (ultralytics로 내보낸 ONNX인지 확인)"
