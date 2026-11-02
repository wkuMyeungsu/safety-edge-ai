# Pi gateway API 정비 교범

| 항목 | 내용 |
|---|---|
| 문서 번호 | SEA-AMM-API-001 |
| 제목 | Pi gateway API 정비 교범 (Edge AI 스마트 산업 안전 시스템) |
| 개정 | 0 |
| 개정일 | 2026-11-02 |
| 적용 대상 (Effectivity) | 라즈베리 파이 `rpi5`, 저장소 `dev` 커밋 `09a4208` 이후, gateway 공개 주소 `https://rpi5.tail7377e4.ts.net` |
| 작성·관리 | 명수 (gateway·Pi 담당) |
| 근거 문서 | `docs/contracts/frame.md`, `inference.md`, `record-storage.md`, `docs/decisions.md` |

## 개정 기록 (Record of Revisions)

| 개정 | 날짜 | 바뀐 절 | 내용 | 작성 |
|---|---|---|---|---|
| 0 | 2026-11-02 | 전체 | 최초 발행 | 명수 |

개정할 때는 이 표에 한 줄을 더하고, 표지의 개정 번호와 개정일을 함께 바꾼다. API가 바뀌는 PR은 이 문서도 같은 PR에서 고친다.

## 유효 절 목록 (List of Effective Sections)

| 절 | 제목 | 개정 |
|---|---|---|
| 00-00-00 | 이 교범을 읽는 법 | 0 |
| 10-00-00 | 일반 (설명과 작동) | 0 |
| 10-10-00 | 엔드포인트 목록 | 0 |
| 20-10-01 | 작업: 상태 확인 (`GET /health`) | 0 |
| 20-20-01 | 작업: 최근 처리 결과 조회 (`GET /recent`) | 0 |
| 20-30-01 | 작업: 프레임 전송, 같은 네트워크 | 0 |
| 20-30-02 | 작업: 프레임 전송, 인터넷 | 0 |
| 30-00-00 | 데이터 사양 (응답 필드·코드) | 0 |
| 40-00-00 | 고장 탐구 (Fault Isolation) | 0 |
| 50-00-00 | 내부 API (참고, 외부 접근 불가) | 0 |
| 부록 A | 용어 | 0 |

---

## 00-00-00 이 교범을 읽는 법

### 1. 경고·주의·참고

> **⚠ 경고 (WARNING)**: 지키지 않으면 실제 데이터가 오염되거나 비밀값이 새어 나간다. 반드시 지킨다.

> **△ 주의 (CAUTION)**: 지키지 않으면 작업이 실패하거나 다른 사람의 작업을 방해한다.

> **참고 (NOTE)**: 작업을 쉽게 하는 정보다.

### 2. 번호 체계

`장-절-주제`. 예: `20-30-02`는 20장(작업), 30절(프레임 전송), 2번 주제(인터넷). 작업 카드의 단계는 `A.` → `(1)` → `(a)` 순서로 나눈다.

### 3. 문장 규칙

한 문장에 한 동작을 쓴다. 명령형으로 쓴다. 값은 `코드 글꼴`로 쓴다.

---

## 10-00-00 일반 (설명과 작동)

### 1. 목적

이 교범은 라즈베리 파이 gateway가 제공하는 API와, 그 API를 쓰는 작업 절차를 정한다. 대상은 팀원 전원이다.

### 2. 시스템 구성

```
[ESP32 / PC] ──JPEG──▶ gateway :8001 ──▶ inference :8003 (안전모·조끼 판정)
                           │
                           └─(위반이면)──▶ uploader :8004 ──▶ Supabase (safety_logs, violations 버킷) ◀── 웹
```

- gateway는 사진을 받으면 대기 줄에 넣고 바로 `202`로 답한다. 판정은 기다리지 않는다.
- 작업자 1개가 대기 줄에서 한 장씩 꺼내 inference에 판정을 맡긴다.
- 판정이 `fail`이면 uploader에 넘긴다. uploader가 Supabase에 저장한다.
- 판정 결과는 ESP32에 돌려주지 않는다. `GET /recent`, Supabase, 웹에서 본다.

### 3. 접근 경로

| 경로 | 주소 | 토큰 | 쓰는 곳 |
|---|---|---|---|
| 같은 네트워크 | `http://172.30.1.68:8001` | 필요 없음 | 명수 집 네트워크의 ESP32·PC |
| 인터넷 (Tailscale Funnel) | `https://rpi5.tail7377e4.ts.net` | `POST /frame`에만 필요 | 다른 곳의 ESP32·PC |

> **참고**: Pi 주소 `172.30.1.68`은 공유기 DHCP 예약 전에는 바뀔 수 있다. 바뀌면 이 표를 개정한다.

> **참고**: 외부에 열린 것은 gateway(8001)뿐이다. inference, uploader, SSH는 인터넷에서 접근할 수 없다.

### 4. 인증

| 요청 | 인증 |
|---|---|
| 같은 네트워크의 모든 요청 | 없음 |
| 인터넷의 `GET /health`, `GET /recent` | 없음 (공개) |
| 인터넷의 `POST /frame` | `X-Device-Token` 헤더가 Pi `pi/.env`의 `GATEWAY_TOKEN`과 같아야 한다 |

- gateway는 프록시 헤더(`X-Forwarded-For`, `Forwarded`, `Cf-Connecting-Ip`, `Tailscale-Funnel-Request`)가 있으면 인터넷 요청으로 본다.
- `GATEWAY_TOKEN`이 비어 있으면 인터넷의 `POST /frame`은 모두 `401`이다.

> **⚠ 경고**: 토큰을 커밋, PR, 이슈, 공개 채팅에 쓰지 않는다. 토큰은 Pi `pi/.env`와 각자의 `config.h`에만 둔다. 명수에게 개인 메시지로 받는다.

> **△ 주의**: 인터넷의 `GET /health`, `GET /recent`는 토큰 없이 누구나 볼 수 있다. 장치 ID와 판정 결과가 보인다. 장치 ID에 개인정보를 넣지 않는다.

### 5. 공통 규칙

| 항목 | 규칙 |
|---|---|
| 응답 형식 | JSON (`Content-Type: application/json`) |
| 시각 | UTC, ISO 8601 (예: `2026-11-02T04:22:10.873519+00:00`) |
| 장치 ID | 영문·숫자·`-`·`_`, 1~64자. 팀원 ESP32는 `cam-<이름>`, 테스트는 `test-<아무거나>` (`docs/contracts/frame.md`) |
| 사진 | JPEG 바이트 그대로, 2MB 이하 |

> **⚠ 경고**: 위반으로 판정된 사진은 실제 Supabase에 저장되고 웹에 나온다. 시험 전송에는 반드시 `test-`로 시작하는 장치 ID를 쓴다. 그래야 시험 기록만 골라 지울 수 있다.

### 6. 성능 기준값

| 항목 | 값 | 측정 조건 |
|---|---|---|
| 추론 시간 (`infer_ms`) | 중앙값 445ms, 최대 505ms | Pi 5, 커밋 `adbb7a8`, 사진 15장 한 장씩 |
| 받은 뒤 처리 끝까지 (`total_ms`) | 중앙값 455ms, 최대 589ms | 같음 (위반 아님, uploader 호출 없음) |
| 대기 줄 | 4장 (`QUEUE_MAX`) | 처리 중 1장 + 대기 4장을 넘으면 `503` |

---

## 10-10-00 엔드포인트 목록

| 메서드 | 경로 | 하는 일 | 인터넷 토큰 | 작업 카드 |
|---|---|---|---|---|
| `GET` | `/health` | gateway 상태, 대기 줄, 처리 건수 | 필요 없음 | 20-10-01 |
| `GET` | `/recent` | 최근 처리 결과 50건 | 필요 없음 | 20-20-01 |
| `POST` | `/frame` | 사진 전송 (판정 요청) | **필요** | 20-30-01, 20-30-02 |

---

## 20-10-01 작업: 상태 확인 (`GET /health`)

### A. 목적

gateway가 살아 있는지, 대기 줄이 얼마나 찼는지, 지금까지 몇 장을 처리했는지 확인한다.

### B. 참조

| 참조 | 제목 |
|---|---|
| 30-00-00 1항 | `/health` 응답 필드 |
| 40-00-00 | 고장 탐구 |

### C. 필요 장비

| 장비 | 용도 |
|---|---|
| 브라우저 또는 `curl` | 요청 보내기 |

### D. 작업 준비

(1) 접근 경로를 고른다 (10-00-00 3항).

### E. 절차

(1) 아래 주소를 브라우저로 연다. 또는 명령을 실행한다.

```bash
curl https://rpi5.tail7377e4.ts.net/health
```

### F. 결과 확인

(1) 응답 코드가 `200`인지 확인한다.

(2) `status`가 `"ok"`인지 확인한다.

(3) `queue`가 `queue_max`보다 작은지 확인한다. 같으면 새 사진은 `503`으로 거절된다.

```json
{"service": "gateway", "status": "ok", "queue": 0, "queue_max": 4,
 "stats": {"received": 18, "verdict_fail": 11, "verdict_pass": 5, "upload_stored": 1, "unauthorized": 2}}
```

### G. 마무리

없음.

---

## 20-20-01 작업: 최근 처리 결과 조회 (`GET /recent`)

### A. 목적

보낸 사진이 어떻게 판정되었고, Supabase에 저장되었는지 확인한다.

### B. 참조

| 참조 | 제목 |
|---|---|
| 30-00-00 2항 | `/recent` 응답 필드 |

### C. 필요 장비

| 장비 | 용도 |
|---|---|
| 브라우저 또는 `curl` | 요청 보내기 |
| 보낸 장치 ID | 결과 거르기 |

### D. 작업 준비

(1) 확인할 장치 ID를 정한다. 예: `test-woojin`.

### E. 절차

(1) 장치 ID로 걸러서 조회한다.

```bash
curl "https://rpi5.tail7377e4.ts.net/recent?device_id=test-woojin"
```

(2) 장치 ID를 빼면 모든 장치의 결과를 받는다.

> **참고**: 최근 50건만 보관한다. gateway를 다시 시작하면 비워진다. 오래 남길 기록은 Supabase에서 본다.

### F. 결과 확인

(1) `items`가 최근 것부터 나오는지 확인한다.

(2) 첫 항목의 `verdict`와 `upload`를 아래 표로 판단한다.

| `verdict` | `upload` | 뜻 |
|---|---|---|
| `fail` | `stored` | 위반. Supabase에 저장됨 |
| `fail` | `buffered` | 위반. Pi에 보관, 나중에 Supabase로 올림 |
| `fail` | `error` | 위반. uploader 호출 실패 (40-00-00) |
| `pass` | `null` | 안전모·조끼 모두 착용. 저장하지 않음 |
| `no_person` | `null` | 모델이 사람을 찾지 못함. 저장하지 않음 |
| `error` | `null` | 판정 실패 (40-00-00) |

### G. 마무리

없음.

---

## 20-30-01 작업: 프레임 전송, 같은 네트워크

### A. 목적

Pi와 같은 네트워크에서 사진을 보내 판정을 요청한다.

### B. 참조

| 참조 | 제목 |
|---|---|
| `docs/contracts/frame.md` | 프레임 전송 계약 |
| 30-00-00 3항 | `/frame` 응답 코드 |

### C. 필요 장비

| 장비 | 용도 |
|---|---|
| ESP32 (펌웨어 `safety_cam`) 또는 `curl` | 보내기 |
| JPEG 사진 (2MB 이하) | 판정 대상 |

### D. 작업 준비

(1) 장비가 Pi와 같은 네트워크에 있는지 확인한다.

(2) 장치 ID를 정한다 (10-00-00 5항).

> **⚠ 경고**: 시험 전송이면 장치 ID를 `test-`로 시작하게 한다.

### E. 절차

(1) ESP32: `config.h`를 아래처럼 쓴다. 토큰은 비워 둔다.

```c
#define GATEWAY_URL   "http://172.30.1.68:8001/frame"
#define DEVICE_ID     "cam-<이름>"
```

(2) PC: 아래 명령을 실행한다.

```bash
curl -H "X-Device-Id: test-<이름>" -H "Content-Type: image/jpeg" \
     --data-binary @사진.jpg http://172.30.1.68:8001/frame
```

(3) 선택: 사람 감지 점수와 사람 수를 함께 보낸다 (`X-Person-Score`, `X-Person-Count`). ESP32 펌웨어는 자동으로 보낸다.

### F. 결과 확인

(1) 응답 코드가 `202`이고 본문이 `{"status": "queued", ...}`인지 확인한다.

(2) 1초쯤 기다린 뒤 20-20-01로 판정 결과를 확인한다.

### G. 마무리

(1) 시험 기록은 Supabase에서 `device_id`가 `test-`로 시작하는 행을 지운다 (도은에게 요청).

---

## 20-30-02 작업: 프레임 전송, 인터넷

### A. 목적

Pi와 다른 네트워크(집 등)에서 사진을 보내 판정을 요청한다.

### B. 참조

| 참조 | 제목 |
|---|---|
| `docs/contracts/frame.md` "인터넷으로 보낼 때" | 프레임 전송 계약 |
| `docs/decisions.md` 2026-11-02 Tailscale Funnel | 공개 방식 결정 |
| 30-00-00 3항 | `/frame` 응답 코드 |

### C. 필요 장비

| 장비 | 용도 |
|---|---|
| ESP32 또는 `curl` | 보내기. ESP32는 HTTPS와 토큰을 지원하는 펌웨어가 필요하다 |
| JPEG 사진 (2MB 이하) | 판정 대상 |
| 팀 공용 토큰 | 인증. 명수에게 개인 메시지로 받는다 |

> **△ 주의**: 펌웨어 `safety_cam` 0.3.0은 HTTPS와 토큰 헤더를 지원하지 않는다. 이 버전으로 인터넷 주소에 보내면 실패한다. HTTPS와 토큰을 지원하는 버전이 병합되면 이 교범을 개정한다.

### D. 작업 준비

(1) 토큰을 받는다.

(2) 장치 ID를 정한다 (10-00-00 5항).

> **⚠ 경고**: 토큰을 커밋하지 않는다. `config.h`는 `.gitignore`에 들어 있다. 커밋 전에 `git status`로 `config.h`가 없는지 확인한다.

### E. 절차

(1) ESP32: `config.h`를 아래처럼 쓴다.

```c
#define GATEWAY_URL   "https://rpi5.tail7377e4.ts.net/frame"
#define DEVICE_ID     "cam-<이름>"
#define GATEWAY_TOKEN "<토큰>"
```

(2) PC: 아래 명령을 실행한다.

```bash
curl -H "X-Device-Id: test-<이름>" -H "X-Device-Token: <토큰>" -H "Content-Type: image/jpeg" \
     --data-binary @사진.jpg https://rpi5.tail7377e4.ts.net/frame
```

### F. 결과 확인

(1) 응답 코드가 `202`인지 확인한다. `401`이면 토큰을 확인한다 (40-00-00).

(2) 20-20-01로 판정 결과를 확인한다.

### G. 마무리

(1) 시험 기록은 20-30-01 G항과 같이 지운다.

---

## 30-00-00 데이터 사양

### 1. `GET /health` 응답 (`200`)

| 필드 | 형식 | 뜻 |
|---|---|---|
| `service` | 문자열 | 항상 `"gateway"` |
| `status` | 문자열 | 항상 `"ok"` (답하면 살아 있는 것) |
| `queue` | 정수 | 대기 중인 사진 수 |
| `queue_max` | 정수 | 대기 줄 크기 (`QUEUE_MAX`, 기본 4) |
| `stats` | 객체 | gateway 시작 후 누적 건수. 0인 항목은 빠진다 |

`stats` 키:

| 키 | 뜻 |
|---|---|
| `received` | 대기 줄에 넣은 사진 |
| `rejected` | `400`·`413`으로 거절 |
| `unauthorized` | `401`로 거절 (토큰) |
| `busy` | `503`으로 거절 (대기 줄 가득 참) |
| `verdict_pass`, `verdict_fail`, `verdict_no_person`, `verdict_error` | 판정 결과별 |
| `upload_stored`, `upload_buffered`, `upload_error` | 위반 저장 결과별 |

### 2. `GET /recent` 응답 (`200`)

질의 변수: `device_id` (선택). 응답: `{"items": [ ... ]}`, 최근 것부터, 최대 50건.

| 필드 | 형식 | 뜻 |
|---|---|---|
| `device_id` | 문자열 | 보낸 장치 |
| `received_at` | 문자열 (UTC) | gateway가 받은 시각. Supabase `created_at`이 된다 |
| `wait_ms` | 정수 | 대기 줄에서 기다린 시간 |
| `person_score` | 숫자 \| null | ESP32 사람 감지 점수 (`X-Person-Score`) |
| `person_count` | 정수 \| null | ESP32가 찾은 사람 수 (`X-Person-Count`) |
| `verdict` | 문자열 | `pass` · `fail` · `no_person` · `error` |
| `has_helmet` | bool | 모두 안전모를 썼는지 (판정 실패면 없음) |
| `has_vest` | bool | 모두 조끼를 입었는지 (판정 실패면 없음) |
| `confidence` | 숫자 | 판정 신뢰도 0~1 (판정 실패면 없음) |
| `infer_ms` | 정수 | inference 추론 시간 (판정 실패면 없음) |
| `upload` | 문자열 \| null | `stored` · `buffered` · `error`. 위반이 아니면 `null` |
| `total_ms` | 정수 | 받은 뒤 처리 끝까지 걸린 시간 |

### 3. `POST /frame`

요청 헤더:

| 헤더 | 필수 | 값 |
|---|---|---|
| `Content-Type` | 예 | `image/jpeg` |
| `X-Device-Id` | 예 | 장치 ID (10-00-00 5항) |
| `X-Device-Token` | 인터넷이면 예 | 팀 공용 토큰 |
| `X-Person-Score` | 아니오 | 0~1. 숫자가 아니면 `null`로 기록하고 사진은 받는다 |
| `X-Person-Count` | 아니오 | 정수. 숫자가 아니면 `null`로 기록하고 사진은 받는다 |

본문: JPEG 바이트 그대로 (`FF D8 FF`로 시작), 2MB 이하. multipart가 아니다.

응답:

| 코드 | 본문 `status` | 뜻 | 보낸 쪽이 할 일 |
|---|---|---|---|
| `202` | `queued` | 대기 줄에 넣음. `queue`는 지금 대기 수 | 없음 |
| `400` | `rejected` | 장치 ID 형식 틀림, 본문이 JPEG가 아님 | 버린다. `detail`을 보고 설정을 고친다 |
| `401` | `rejected` | 인터넷 요청인데 토큰이 없거나 틀림 | 버린다. 토큰을 확인한다 |
| `413` | `rejected` | 2MB 초과 | 버린다. 해상도·품질을 낮춘다 |
| `503` | `busy` | 대기 줄 가득 참 | 버린다. 다시 보내지 않는다 (다음 프레임이 더 최신) |

오류 본문은 `{"status": "...", "detail": "<이유>"}`.

---

## 40-00-00 고장 탐구 (Fault Isolation)

먼저 20-10-01로 gateway가 답하는지 확인한다. 답하지 않으면 1번부터 본다.

| 번호 | 증상 | 가능한 원인 | 조치 |
|---|---|---|---|
| 1 | 인터넷 주소가 응답 없음, TLS 오류 | Pi 꺼짐, 네트워크 끊김, Funnel 꺼짐 | 명수에게 알린다. 명수는 Pi에서 `tailscale funnel status`, `docker compose ps`를 확인한다 |
| 2 | 같은 네트워크 주소가 응답 없음 | Pi IP 바뀜, 다른 네트워크에 있음 | `ping rpi5.local` 또는 공유기에서 Pi IP를 확인한다 |
| 3 | `401` | 토큰 없음, 오타, 토큰이 바뀜 | 토큰을 다시 받는다. 앞뒤 공백을 지운다 |
| 4 | `400` "X-Device-Id" | 장치 ID에 한글·공백·특수문자 | 영문·숫자·`-`·`_`만 쓴다 |
| 5 | `400` "JPEG가 아님" | PNG 등 다른 형식, multipart로 보냄 | JPEG 바이트를 본문에 그대로 보낸다 (`--data-binary @파일`) |
| 6 | `503` 이 자주 남 | 너무 빨리 보냄 (초당 2장 이상) | 전송 간격을 늘린다. ESP32는 쿨다운을 늘린다 |
| 7 | `/recent`에서 `verdict: error` | inference 오류, 모델 없음 | 명수에게 알린다. inference 로그를 본다 |
| 8 | `upload: buffered`가 계속됨 | Supabase 연결 안 됨 | 잃은 기록은 없다 (Pi에 보관). 도은에게 알린다 |
| 9 | `upload: error` | uploader가 거절함 (`4xx`) | 명수와 도은에게 알린다. uploader 로그를 본다 |
| 10 | `202`인데 `/recent`에 없음 | 50건이 넘어 밀려남, gateway 재시작 | 장치 ID로 걸러서 다시 본다. Supabase에서 확인한다 |

---

## 50-00-00 내부 API (참고, 외부 접근 불가)

Pi 안의 컨테이너끼리만 부른다. 인터넷과 같은 네트워크에서 직접 부를 수 없다. PC에서 `docker-compose.ci.yml`로 띄우면 시험용으로 열린다.

| 서비스 | 메서드·경로 | 하는 일 | 계약 |
|---|---|---|---|
| inference `:8003` | `POST /predict` | JPEG → 판정 JSON (`verdict`, `has_helmet`, `has_vest`, `confidence`, `detections`, `infer_ms` 등) | `docs/contracts/inference.md` |
| inference `:8003` | `GET /health` | 모델을 불러왔는지 (`model_loaded`) | 같음 |
| uploader `:8004` | `POST /records` | multipart(`result` JSON + `image`) → Supabase 저장. `201` 저장, `202` Pi에 보관 | `docs/contracts/record-storage.md` |
| uploader `:8004` | `GET /health` | Supabase 설정 여부, 보관 중인 건수 (`buffered`) | 같음 |

---

## 부록 A 용어

| 용어 | 뜻 |
|---|---|
| gateway | Pi에서 사진을 받아 판정과 저장 순서를 관리하는 서비스 |
| inference | 안전모·조끼 착용을 판정하는 서비스 (YOLOv8 ONNX) |
| uploader | 위반 기록을 Supabase에 저장하는 서비스. 실패하면 Pi에 보관했다가 다시 보낸다 |
| Funnel | Tailscale Funnel. Pi의 gateway를 인터넷 HTTPS 주소로 여는 기능 |
| 대기 줄 | gateway가 받은 사진을 판정 전까지 넣어 두는 곳 |
| 장치 ID | 사진을 보낸 장치의 이름. `X-Device-Id` |
| 팀 공용 토큰 | 인터넷 전송을 허락하는 비밀값. `X-Device-Token` |
