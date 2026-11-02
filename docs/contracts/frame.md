# 프레임 전송: esp32 → pi gateway

- 상태: **초안** (명수 제안, 대희 펌웨어 #18에 맞춤). 대희가 확인하면 "합의"로 바꾼다.
- 확인할 담당: 대희 (esp32, 보내는 쪽), 명수 (gateway, 받는 쪽)

ESP32는 사람을 감지한 프레임만 보낸다. gateway는 받자마자 대기 줄에 넣고 바로 답한다 (판정을 기다리지 않는다).

## 요청

```
POST http://<Pi IP>:8001/frame
Content-Type: image/jpeg
X-Device-Id: cam-myeungsu

<카메라 JPEG 바이트 그대로>
```

| 항목 | 규칙 |
|---|---|
| 본문 | JPEG 바이트 그대로 (multipart 아님). `FF D8 FF`로 시작해야 한다 |
| 크기 | 2MB 이하 (inference 제한과 같다) |
| 해상도 | 지금 펌웨어는 QVGA 320×240, JPEG 품질 12 (10~20KB). 판정 정확도가 모자라면 VGA 640×480까지 올린다 (모델 입력이 640이라 그 이상은 의미 없음) |
| `X-Device-Id` | 필수. 영문·숫자·`-`·`_`, 1~64자. `config.h`의 `DEVICE_ID`. 이름 규칙은 아래 "장치 ID" 절 |
| `X-Person-Score` | 선택. ESP32 사람 감지 점수 (0~1). gateway는 `/recent`에 기록만 한다 |
| `X-Person-Count` | 선택. ESP32가 찾은 사람 수. gateway는 `/recent`에 기록만 한다 |
| `X-Device-Token` | **인터넷으로 보낼 때만** 필수 (아래 절). 같은 네트워크에서는 보내지 않아도 된다 |

선택 헤더가 없거나 숫자가 아니어도 사진은 받는다 (값만 `null`).

```bash
curl -H "X-Device-Id: test-curl" -H "Content-Type: image/jpeg" \
     --data-binary @frame.jpg http://localhost:8001/frame
```

## 장치 ID

누가 보낸 기록인지 `device_id`로 구분한다 (Supabase `safety_logs.device_id`, 사진 경로 `violations/<device_id>/…`, 웹 장치 필터).

| 용도 | 형식 | 예 |
|---|---|---|
| 팀원 각자의 ESP32 | `cam-<이름>` | `cam-myeungsu`, `cam-daehee`, `cam-woojin`, `cam-doeun`, `cam-jina` |
| 테스트 (curl, pytest, 시험 전송) | `test-<아무거나>` | `test-funnel`, `test-curl` |

- 같은 ID를 두 장치가 쓰지 않는다. `config.example.h`의 기본값을 그대로 쓰지 않는다.
- 테스트 기록은 `device_id`가 `test-`로 시작하므로 골라서 지울 수 있다.
- 시연용으로 따로 설치하는 카메라가 생기면 이 표에 규칙을 더한다.

## 응답

| 코드 | 본문 | 뜻 | ESP32가 할 일 |
|---|---|---|---|
| `202` | `{"status": "queued", "queue": 1, "frame": "ab12cd34"}` | 대기 줄에 넣음 | 쿨다운 후 다음 감지 |
| `400` | `{"status": "rejected", "detail": "…"}` | `X-Device-Id`가 없거나 틀림, 본문이 JPEG가 아님 | 버린다. 시리얼에 detail 출력 (설정·코드 문제) |
| `401` | 〃 | 인터넷으로 보냈는데 `X-Device-Token`이 없거나 틀림 | 버린다. `config.h`의 토큰을 확인한다 |
| `413` | 〃 | 2MB 초과 | 버린다. 해상도·품질을 낮춘다 |
| `503` | `{"status": "busy", "detail": "…"}` | 대기 줄이 가득 참 | 버린다 (재시도하지 않는다. 다음 감지 프레임이 더 최신이다) |

- 연결 실패·응답 없음은 ESP32 쪽 HTTP 제한 시간(권장 5초)으로 끊고 버린다.
- `frame`은 gateway가 붙인 사진 번호(8자리 hex)다. gateway·inference·uploader 로그에 `frame=`으로 찍히므로, ESP32 시리얼에 찍힌 202 본문으로 Pi 로그를 찾는다. ESP32가 따로 처리할 필요는 없다.
- 판정 결과는 ESP32에 돌려주지 않는다. 위반 기록은 Supabase와 웹에서 본다.

## 인터넷으로 보낼 때 (Pi와 다른 네트워크의 ESP32)

Pi는 명수 집 네트워크에 있다. 다른 곳의 ESP32는 Tailscale Funnel이 열어 주는 HTTPS 주소로 보낸다.

```
POST https://<Pi 이름>.<tailnet>.ts.net/frame
Content-Type: image/jpeg
X-Device-Id: cam-daehee
X-Device-Token: <팀 공용 토큰>
```

| 같은 네트워크 | 인터넷 |
|---|---|
| `http://<Pi IP>:8001/frame` | `https://<Pi 이름>.<tailnet>.ts.net/frame` |
| 토큰 없음 | `X-Device-Token` 필수 |
| `HTTPClient.begin(url)` | `WiFiClientSecure` + `HTTPClient.begin(client, url)` |

- gateway는 프록시가 붙이는 헤더(`X-Forwarded-For`, `Forwarded`, `Cf-Connecting-Ip`, `Tailscale-Funnel-Request`)가 있으면 인터넷 요청으로 보고 토큰을 검사한다.
- 토큰은 Pi의 `pi/.env`(`GATEWAY_TOKEN`)와 각자의 `config.h`에만 둔다. 커밋하지 않고, 팀원에게는 개인 메시지로 전한다.
- `GATEWAY_TOKEN`이 비어 있으면 인터넷 요청은 모두 401이다 (실수로 열린 채로 두지 않게).

## gateway 처리 순서 (참고)

1. 받은 시각(UTC)을 `detected_at`으로 기록하고 대기 줄(기본 4장)에 넣는다.
2. 작업자 1개가 하나씩 꺼내 `inference /predict`를 부른다 ([inference.md](inference.md)).
3. `verdict`가 `fail`이면 `uploader /records`로 넘긴다 ([record-storage.md](record-storage.md)). `pass`·`no_person`·오류는 로그만 남긴다.

디버깅: `GET /health` (대기 줄 길이·처리 건수), `GET /recent?device_id=cam-01` (최근 처리 결과 50건, ESP32 감지 점수 포함).
