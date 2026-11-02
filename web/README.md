# web

위반 기록을 보여 주는 정적 페이지. Supabase를 anon key로 조회만 한다 (쓰기 권한 없음).
빌드 없이 `index.html` + `style.css` + `app.js` + `config.js`로 돈다.

| 화면 | 데이터 |
|---|---|
| 위반 기록 목록 | `safety_logs` 최신순, 50건씩 더 보기. 기간(오늘·7일·전체)·위반 종류·장치 필터 |
| 위반 사진 썸네일 | `safety_logs.image_url` (violations 버킷). 누르면 크게 보기 |
| 오늘 위반 수 | `safety_logs`의 오늘 날짜 행 수, 안전모·조끼 미착용 수, 마지막 감지 |
| 실시간 갱신 | Supabase Realtime, `safety_logs` INSERT 구독 → 목록 맨 위·오늘 수치에 바로 반영 |

- 테이블 컬럼은 `cloud/supabase/schema.sql`과 `docs/contracts/`가 기준이다. 컬럼이 바뀌면 cloud 담당과 먼저 맞춘다.
- service key는 넣지 않는다. Supabase URL과 anon key만 쓴다.
- Supabase에 데이터가 아직 없으면 SQL Editor로 예시 행을 넣어 화면을 먼저 만든다. Pi 없이 개발할 수 있다.

## 연결

`config.js`에 Supabase 대시보드 → Project Settings → API의 Project URL과 anon(public) key를 넣는다.
두 값이 비어 있으면 가짜 데이터로 도는 **데모 모드**로 열려서, Supabase가 없어도 화면을 확인할 수 있다.

## 로컬에서 보기

```bash
cd web
python3 -m http.server 8080   # http://localhost:8080
```

## 웹이 읽는 것

- `safety_logs` 컬럼: `id, created_at, device_id, has_helmet, has_vest, confidence, image_url`
- anon 읽기 RLS, `supabase_realtime` publication에 `safety_logs` 포함
- `image_url`은 브라우저에서 바로 열리는 공개 URL

테스트는 `tests/web/test_web.py`: service key 유출 검사, 웹이 읽는 컬럼이 `schema.sql`에 있는지, 참조 파일 존재.
