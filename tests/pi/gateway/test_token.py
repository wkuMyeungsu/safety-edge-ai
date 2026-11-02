"""인터넷을 거친 요청의 토큰 검사 (docs/contracts/frame.md "인터넷으로 보낼 때").

프록시가 붙이는 X-Forwarded-For가 있으면 인터넷 요청으로 본다.
토큰 값은 docker-compose.ci.yml과 같다. 다른 값으로 띄웠으면 GATEWAY_TOKEN 환경 변수로 넘긴다.
"""

import os

import pytest
import requests

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"
TOKEN = os.environ.get("GATEWAY_TOKEN", "ci-test-token")
VIA_PROXY = {"X-Forwarded-For": "203.0.113.7"}


def post(url, extra=None):
    headers = {"Content-Type": "image/jpeg", "X-Device-Id": "test-token", **(extra or {})}
    return requests.post(f"{url}/frame", data=JPEG, headers=headers, timeout=10)


def test_local_request_needs_no_token(gateway_url):
    assert post(gateway_url).status_code == 202


@pytest.mark.parametrize("token", [None, "", "wrong-token"])
def test_proxied_request_without_valid_token_is_401(gateway_url, token):
    extra = dict(VIA_PROXY)
    if token is not None:
        extra["X-Device-Token"] = token
    r = post(gateway_url, extra)
    assert r.status_code == 401
    assert r.json()["status"] == "rejected"


@pytest.mark.parametrize("proxy_header", [VIA_PROXY, {"Tailscale-Funnel-Request": "?1"}, {"Cf-Connecting-Ip": "203.0.113.7"}])
def test_proxied_request_with_token_is_queued(gateway_url, proxy_header):
    r = post(gateway_url, {**proxy_header, "X-Device-Token": TOKEN})
    assert r.status_code == 202, r.text
