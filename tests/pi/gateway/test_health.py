import requests


def test_health(gateway_url):
    r = requests.get(f"{gateway_url}/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["service"] == "gateway"
