# 기록 저장: pi gateway → pi uploader

확인할 담당: 명수(gateway), 도은(uploader)

gateway는 inference 판정이 fail일 때만 uploader에 판정 결과와 사진을 넘긴다. pass는 넘기지 않는다.

## 요청

`POST http://uploader:8004/records`, `multipart/form-data`

| 파트 | 형식 | 내용 |
|---|---|---|
| `result` | JSON 문자열 | 아래 필드 |
| `image` | `image/jpeg` 파일 | ESP32가 보낸 원본 JPEG 그대로, 5MB 이하 |

`result` 필드:

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `device_id` | string | 예 | ESP32가 보낸 장치 ID. 영문·숫자·`-`·`_`, 1~64자 |
| `has_helmet` | boolean | 예 | 안전모 착용 여부 |
| `has_vest` | boolean | 예 | 조끼 착용 여부 |
| `confidence` | number \| null | 아니오 | 판정 신뢰도 0~1 |
| `detected_at` | string | 아니오 | gateway가 사진을 받은 시각, ISO 8601 (시간대 포함). 없으면 uploader가 받은 시각 |
| `persons` | 정수 | 아니오 | 사진 속 사람 수. 연속 위반 묶기(아래)에 쓴다. 없거나 틀리면 사람 수는 비교하지 않는다 |

`has_helmet`과 `has_vest` 중 하나 이상은 `false`여야 한다 (위반만 저장).

`has_helmet` `has_vest` `confidence` `persons`는 [inference.md](inference.md)의 응답 필드와 같다. gateway는 inference 응답 JSON에 `device_id`(필요하면 `detected_at`)를 더해 그대로 `result`로 넘기면 된다. 위 표에 없는 필드(`verdict`, `detections`, `infer_ms` 등)는 uploader가 무시한다.

## 연속 위반 묶기

ESP32는 사람이 보이는 동안 몇 초마다 사진을 보낸다. 같은 사람이 카메라 앞에 서 있는 동안 위반이 계속 쌓이지 않도록, uploader는 아래 조건이 **모두** 맞으면 같은 위반이 이어지는 것으로 보고 저장하지 않는다 (`202 skipped`).

- 같은 `device_id`
- 위반 종류(`has_helmet`·`has_vest` 조합)가 직전 위반과 같음
- 사진 속 사람 수(`persons`)가 직전보다 늘지 않음
- 직전 위반(저장했든 묶었든)과 `detected_at` 차이가 30초 이내 (`DEDUP_SECONDS`, 0이면 묶지 않음)

위반이 30초 넘게 끊기거나, 위반 종류가 바뀌거나, 사람이 늘면 새 위반으로 저장한다. 그래서 `safety_logs` 한 행은 사진 한 장이 아니라 **위반 한 건**이다.

```bash
curl -F 'result={"device_id":"esp32-01","has_helmet":false,"has_vest":true,"confidence":0.82}' \
     -F 'image=@no_helmet.jpg;type=image/jpeg' \
     http://localhost:8004/records
```

## 응답

| 코드 | 의미 | gateway가 할 일 |
|---|---|---|
| `201` | Supabase에 저장 완료. `{"status": "stored", "id": <safety_logs.id>}` | 없음 |
| `202` | Supabase에 못 보내 버퍼에 저장. `{"status": "buffered"}` uploader가 나중에 다시 보낸다 | 없음 (재시도하지 않는다) |
| `202` | 직전 위반이 이어지는 중이라 저장하지 않음 (연속 위반 묶기). `{"status": "skipped"}` | 없음 |
| `400` | `result`가 JSON이 아니거나 필드가 틀림. pass 판정 포함 | 로그만 남긴다 |
| `413` | 사진이 5MB 초과 | 로그만 남긴다 |
| `415` | 사진이 JPEG가 아님 | 로그만 남긴다 |

- 201·202 모두 정상 처리다. gateway는 두 경우 모두 다음 사진으로 넘어간다. 202는 `status`로 `buffered`와 `skipped`를 구분한다.
- uploader는 Supabase 응답을 10초 넘게 기다리지 않는다. 시간이 넘으면 버퍼에 넣고 202를 돌려준다.
