# web

위반 기록을 보여 주는 정적 페이지. Supabase를 anon key로 조회만 한다 (쓰기 권한 없음).

| 화면 | 데이터 |
|---|---|
| 위반 기록 목록 | `safety_logs` 최신순 |
| 위반 사진 썸네일 | `safety_logs.image_url` (violations 버킷) |
| 오늘 위반 수 | `safety_logs`의 오늘 날짜 행 수 |
| 실시간 갱신 | Supabase Realtime, `safety_logs` INSERT 구독 |

- 테이블 컬럼은 `cloud/supabase/schema.sql`과 `docs/contracts/`가 기준이다. 컬럼이 바뀌면 cloud 담당과 먼저 맞춘다.
- service key는 넣지 않는다. Supabase URL과 anon key만 쓴다.
- Supabase에 데이터가 아직 없으면 SQL Editor로 예시 행을 넣어 화면을 먼저 만든다. Pi 없이 개발할 수 있다.
