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

`has_helmet`과 `has_vest` 중 하나 이상은 `false`여야 한다 (위반만 저장).

`has_helmet` `has_vest` `confidence`는 [inference.md](inference.md)의 응답 필드와 같다. gateway는 inference 응답 JSON에 `device_id`(필요하면 `detected_at`)를 더해 그대로 `result`로 넘기면 된다. 위 표에 없는 필드(`verdict`, `persons`, `detections`, `infer_ms` 등)는 uploader가 무시한다.

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
| `400` | `result`가 JSON이 아니거나 필드가 틀림. pass 판정 포함 | 로그만 남긴다 |
| `413` | 사진이 5MB 초과 | 로그만 남긴다 |
| `415` | 사진이 JPEG가 아님 | 로그만 남긴다 |

- 201·202 모두 정상 처리다. gateway는 두 경우 모두 다음 사진으로 넘어간다.
- uploader는 Supabase 응답을 10초 넘게 기다리지 않는다. 시간이 넘으면 버퍼에 넣고 202를 돌려준다.
