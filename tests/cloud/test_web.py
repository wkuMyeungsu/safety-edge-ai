"""cloud/web 정적 페이지 검사.

- 웹 폴더에 service key가 들어가지 않았는지
- 페이지가 참조하는 파일이 모두 있는지
- (supabase) 웹이 읽는 컬럼을 anon key로 조회할 수 있고, anon은 쓸 수 없는지
"""

import os
import re
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "cloud" / "web"

# 웹(app.js)이 safety_logs에서 읽는 컬럼. 스키마와 어긋나면 아래 supabase 테스트가 실패한다.
WEB_COLUMNS = "id,created_at,device_id,has_helmet,has_vest,confidence,image_url"

# supabase start 가 만드는 로컬 기본 anon key (공개된 데모 값). 환경변수로 바꿀 수 있다.
LOCAL_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
    "CRXP1A7WOeoJeXxjNni7tCeb3oJn8E-ozEIvkO72Z0c"
)


def _web_files():
    return [p for p in WEB.rglob("*") if p.is_file()]


def test_web_has_no_service_key():
    for path in _web_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert '"role":"service_role"' not in text, path
        assert "SUPABASE_SERVICE_KEY" not in text, path
        assert not re.search(r"sb_secret_[A-Za-z0-9_-]+", text), path


def test_web_columns_match_app():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert f'"{WEB_COLUMNS}"' in app


def test_index_references_existing_files():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="([^"#:]+)"', html)
    assert refs, "index.html이 로컬 파일을 하나도 참조하지 않음"
    for ref in refs:
        assert (WEB / ref).is_file(), f"index.html이 참조하는 {ref} 없음"


@pytest.fixture(scope="module")
def supabase_rest():
    url = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54321").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", LOCAL_ANON_KEY)
    try:
        requests.get(f"{url}/rest/v1/", timeout=3)
    except requests.RequestException:
        pytest.skip(f"Supabase에 연결할 수 없음: {url}")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    return f"{url}/rest/v1/safety_logs", headers


@pytest.mark.supabase
def test_anon_can_read_web_columns(supabase_rest):
    endpoint, headers = supabase_rest
    r = requests.get(
        endpoint,
        params={"select": WEB_COLUMNS, "order": "created_at.desc", "limit": "1"},
        headers=headers,
        timeout=5,
    )
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


@pytest.mark.supabase
def test_anon_cannot_insert(supabase_rest):
    endpoint, headers = supabase_rest
    r = requests.post(
        endpoint,
        json={"device_id": "test-anon", "has_helmet": False, "has_vest": True},
        headers={**headers, "Prefer": "return=minimal"},
        timeout=5,
    )
    assert r.status_code in (401, 403), r.status_code
