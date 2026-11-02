import requests


def test_health(inference_url):
    r = requests.get(f"{inference_url}/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["service"] == "inference"
