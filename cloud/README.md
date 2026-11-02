# cloud

Supabase(테이블·버킷·RLS)와, 그곳에 기록을 쓰는 uploader를 맡는다.

| 폴더 | 내용 |
|---|---|
| `supabase/` | 테이블·버킷·RLS를 만드는 SQL. Supabase SQL Editor에서 실행한다. CI는 로컬 Supabase에 적용해 본다. |
| `../pi/uploader/` | 판정 결과·위반 사진을 Supabase에 저장하는 컨테이너. Pi에서 돌기 때문에 폴더는 `pi/` 아래에 있고, 담당은 cloud다. |

- 쓰기는 uploader의 service key로만 한다. 웹은 anon key로 읽기만 한다.
- uploader는 PC의 Docker에서 개발한다. `.env`가 없으면 버퍼(`pi/buffer/`)에 쌓는 동작부터 만들 수 있다.
- 테이블 컬럼을 바꾸면 `docs/contracts/`를 고치고 web 담당에게 먼저 알린다.
