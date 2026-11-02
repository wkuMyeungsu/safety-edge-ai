"""web/ 정적 페이지 검사 (CI web job: Supabase 없이 돈다).

- 웹 폴더에 service key가 들어가지 않았는지
- 웹이 읽는 컬럼이 cloud/supabase/schema.sql의 safety_logs에 모두 있는지
- 페이지가 참조하는 로컬 파일이 모두 있는지
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
SCHEMA = ROOT / "cloud" / "supabase" / "schema.sql"

# 웹(app.js)이 safety_logs에서 읽는 컬럼. 바꾸면 app.js의 COLUMNS도 같이 바꾼다.
WEB_COLUMNS = ["id", "created_at", "device_id", "has_helmet", "has_vest", "confidence", "image_url"]


def _web_files():
    return [p for p in WEB.rglob("*") if p.is_file()]


def test_web_has_no_service_key():
    for path in _web_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert '"role":"service_role"' not in text, path
        assert "SUPABASE_SERVICE_KEY" not in text, path
        assert not re.search(r"sb_secret_[A-Za-z0-9_-]+", text), path


def test_app_reads_declared_columns():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert f'"{",".join(WEB_COLUMNS)}"' in app


def test_columns_exist_in_schema():
    sql = SCHEMA.read_text(encoding="utf-8")
    m = re.search(r"create table[^(]*safety_logs\s*\((.*?)\n\);", sql, re.DOTALL | re.IGNORECASE)
    assert m, "schema.sql에서 safety_logs 정의를 찾지 못함"
    defined = {line.split()[0] for line in m.group(1).splitlines() if line.strip()}
    missing = [c for c in WEB_COLUMNS if c not in defined]
    assert not missing, f"schema.sql에 없는 컬럼을 웹이 읽음: {missing}"


def test_index_references_existing_files():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="([^"#:]+)"', html)
    assert refs, "index.html이 로컬 파일을 하나도 참조하지 않음"
    for ref in refs:
        assert (WEB / ref).is_file(), f"index.html이 참조하는 {ref} 없음"
