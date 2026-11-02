import requests


def test_health(uploader_url):
    r = requests.get(f"{uploader_url}/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["service"] == "uploader"
