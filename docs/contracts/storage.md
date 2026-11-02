# 저장 구조 · 조회: pi uploader → cloud → web

확인할 담당: 도은(uploader, Supabase), 진아(web)

테이블·버킷·RLS 정의는 `cloud/supabase/schema.sql`이 기준이다.

## safety_logs

위반(fail) 1건이 1행이다.

| 컬럼 | 타입 | 누가 채우나 | 설명 |
|---|---|---|---|
| `id` | bigint identity | Supabase | 기본 키 |
| `created_at` | timestamptz | uploader | 위반을 감지한 시각 (`detected_at`). 버퍼에서 늦게 올라가도 감지 시각을 유지한다 |
| `device_id` | text | uploader | 장치 ID |
| `has_helmet` | boolean | uploader | 안전모 착용 여부 |
| `has_vest` | boolean | uploader | 조끼 착용 여부 |
| `confidence` | real, null 가능 | uploader | 판정 신뢰도 0~1 |
| `image_url` | text, null 가능 | uploader | 위반 사진의 공개 URL. 브라우저에서 바로 열린다 |

## violations 버킷

- 공개 버킷. JPEG만, 한 장 5MB 이하.
- 경로: `{device_id}/{YYYY-MM-DD}/{uuid}.jpg` (날짜는 `created_at`의 UTC 날짜)
- `image_url` = `{SUPABASE_URL}/storage/v1/object/public/violations/{경로}`
- 버킷 목록 조회 정책은 두지 않는다. URL을 아는 사람만 사진을 연다.

## 권한

| 누가 | 키 | 할 수 있는 것 |
|---|---|---|
| uploader | service key (Pi `.env`에만) | safety_logs 쓰기, 버킷 업로드 |
| web | anon key | safety_logs 읽기, Realtime 구독, `image_url` 열기 |

## 실시간

`supabase_realtime` publication에 `safety_logs`가 들어 있다. web은 INSERT만 구독한다.
