# 파트 간 주고받는 데이터

구현 전에 경계마다 형식을 합의해 이 폴더에 적는다. 합의되면 파일 하나로 정리하고 양쪽 담당자가 확인한다.

| 경계 | 보내는 쪽 → 받는 쪽 | 정할 것 | 문서 |
|---|---|---|---|
| 프레임 전송 | esp32 → pi gateway | 엔드포인트, 이미지 형식·해상도, device_id 전달 방법, 응답 코드 | 미정 |
| 추론 | pi gateway ⇄ pi inference | 요청 형식, 판정 결과 JSON 필드 | 미정 |
| 기록 저장 | pi gateway → pi uploader | 판정 결과 + 사진 전달 형식 | 미정 |
| 저장 구조 | pi uploader → cloud | safety_logs 컬럼, 버킷 이름·경로 규칙 | `cloud/supabase/schema.sql` 초안 |
| 조회 | cloud → web | 화면에 쓰는 컬럼, 사진 URL 형식, 실시간 구독 대상 | `cloud/supabase/schema.sql` 초안 |

| 경계 | 확인할 담당 |
|---|---|
| 프레임 전송 | 대희, 명수 |
| 추론 | 명수, 우진 |
| 기록 저장 | 명수, 도은 |
| 저장 구조 · 조회 | 도은, 진아 |
