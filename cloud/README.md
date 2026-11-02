# cloud

| 폴더 | 내용 |
|---|---|
| `supabase/` | 테이블·버킷·RLS를 만드는 SQL. Supabase SQL Editor에서 실행한다. |
| `web/` | 위반 기록을 보여 주는 정적 페이지. Supabase anon key로 조회만 한다. |

service key는 웹에 넣지 않는다. 웹은 anon key만 쓴다.

## web

빌드 없이 도는 정적 페이지다 (`index.html` + `style.css` + `app.js` + `config.js`).

| 화면 | 내용 |
|---|---|
| 오늘 요약 | 오늘 위반 수, 안전모·조끼 미착용 수, 마지막 감지 시각·장치 |
| 위반 목록 | 시각, 장치, 위반 종류, 신뢰도, 사진 썸네일 (누르면 크게 보기) |
| 필터 | 기간(오늘·7일·전체), 위반 종류, 장치 |
| 실시간 | `safety_logs` INSERT를 구독해 새 위반을 목록 맨 위와 오늘 수치에 바로 반영 |

### 연결

`web/config.js`에 Supabase 대시보드 → Project Settings → API의 Project URL과 anon(public) key를 넣는다.
두 값이 비어 있으면 가짜 데이터로 도는 **데모 모드**로 열려서, Supabase나 Pi가 아직 없어도 화면을 확인할 수 있다.

### 로컬에서 보기

```bash
cd cloud/web
python3 -m http.server 8080   # http://localhost:8080
```

`file://`로 열어도 되지만 브라우저에 따라 막히는 경우가 있어 간단한 서버를 권한다.

### 웹이 기대하는 것 (`supabase/schema.sql`)

- `safety_logs` 컬럼: `id, created_at, device_id, has_helmet, has_vest, confidence, image_url`
- anon 읽기 허용 RLS, `supabase_realtime` publication에 `safety_logs` 포함
- `image_url`은 브라우저에서 바로 열리는 공개 URL (`violations` 버킷 공개 읽기)

테스트는 `tests/cloud/test_web.py` (service key 유출 검사, anon 읽기 가능·쓰기 불가 확인).
