# 프레임 전송: esp32 → pi gateway

- 상태: **초안** (명수 제안). 대희가 확인하면 "합의"로 바꾼다.
- 확인할 담당: 대희 (esp32, 보내는 쪽), 명수 (gateway, 받는 쪽)

ESP32는 사람을 감지한 프레임만 보낸다. gateway는 받자마자 대기 줄에 넣고 바로 답한다 (판정을 기다리지 않는다).

## 요청

```
POST http://<Pi IP>:8001/frame
Content-Type: image/jpeg
X-Device-Id: cam-01

<카메라 JPEG 바이트 그대로>
```

| 항목 | 규칙 |
|---|---|
| 본문 | JPEG 바이트 그대로 (multipart 아님). `FF D8 FF`로 시작해야 한다 |
| 크기 | 2MB 이하 (inference 제한과 같다) |
| 해상도 | 권장 VGA 640×480. 모델 입력이 640이라 더 크게 보내도 정확도는 늘지 않고 전송만 느려진다 |
| `X-Device-Id` | 필수. 영문·숫자·`-`·`_`, 1~64자. `config.h`의 `DEVICE_ID` |

```bash
curl -H "X-Device-Id: cam-01" -H "Content-Type: image/jpeg" \
     --data-binary @frame.jpg http://localhost:8001/frame
```

## 응답

| 코드 | 본문 | 뜻 | ESP32가 할 일 |
|---|---|---|---|
| `202` | `{"status": "queued", "queue": 1}` | 대기 줄에 넣음 | 쿨다운 후 다음 감지 |
| `400` | `{"status": "rejected", "detail": "…"}` | `X-Device-Id`가 없거나 틀림, 본문이 JPEG가 아님 | 버린다. 시리얼에 detail 출력 (설정·코드 문제) |
| `413` | 〃 | 2MB 초과 | 버린다. 해상도·품질을 낮춘다 |
| `503` | `{"status": "busy", "detail": "…"}` | 대기 줄이 가득 참 | 버린다 (재시도하지 않는다. 다음 감지 프레임이 더 최신이다) |

- 연결 실패·응답 없음은 ESP32 쪽 HTTP 제한 시간(권장 5초)으로 끊고 버린다.
- 판정 결과는 ESP32에 돌려주지 않는다. 위반 기록은 Supabase와 웹에서 본다.

## gateway 처리 순서 (참고)

1. 받은 시각(UTC)을 `detected_at`으로 기록하고 대기 줄(기본 4장)에 넣는다.
2. 작업자 1개가 하나씩 꺼내 `inference /predict`를 부른다 ([inference.md](inference.md)).
3. `verdict`가 `fail`이면 `uploader /records`로 넘긴다 ([record-storage.md](record-storage.md)). `pass`·`no_person`·오류는 로그만 남긴다.

디버깅: `GET /health` (대기 줄 길이·처리 건수), `GET /recent?device_id=cam-01` (최근 처리 결과 50건).
