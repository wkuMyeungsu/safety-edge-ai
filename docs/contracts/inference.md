# 추론: pi gateway ⇄ pi inference

- 상태: **합의** (우진 제안, 명수 확인 2026-11-02). 제한 시간은 Pi 5 실측 뒤 다시 본다.
- 확인할 담당: 명수 (gateway, 부르는 쪽), 우진 (inference, 답하는 쪽)

## 요청

```
POST http://inference:8003/predict
Content-Type: image/jpeg
X-Frame-Id: ab12cd34

<ESP32가 보낸 JPEG 바이트 그대로>
```

- `X-Frame-Id`는 선택. gateway가 붙인 사진 번호(8자리 hex)로, inference는 판정에 쓰지 않고 로그(`frame=`)에만 쓴다. 없거나 형식이 틀려도 판정은 그대로 한다.

- 본문은 JPEG 바이트 그대로 보낸다 (multipart 아님). gateway가 ESP32에서 받은 것을 다시 인코딩하지 않는다.
- 최대 2MB. `device_id`는 inference가 쓰지 않으므로 보내지 않는다 (gateway가 들고 있다가 uploader에 넘긴다).
- inference는 한 번에 한 장씩 처리한다. gateway의 처리 작업자 1개와 맞춘다.

## 응답 200

```json
{
  "verdict": "fail",
  "has_helmet": false,
  "has_vest": true,
  "confidence": 0.81,
  "persons": 2,
  "detections": [
    {"label": "Person", "score": 0.93, "box": [102, 40, 260, 470]},
    {"label": "NO-Hardhat", "score": 0.81, "box": [140, 42, 205, 101]}
  ],
  "image": {"width": 640, "height": 480},
  "model": "ppe_yolov8.onnx",
  "infer_ms": 212
}
```

| 필드 | 형식 | 뜻 |
|---|---|---|
| `verdict` | `"pass"` · `"fail"` · `"no_person"` | 판정. gateway는 `fail`일 때만 uploader로 넘긴다 |
| `has_helmet` | bool | 사진 속 사람 **모두** 안전모를 썼으면 true (한 명이라도 안 썼으면 false). `safety_logs.has_helmet` |
| `has_vest` | bool | 사진 속 사람 모두 조끼를 입었으면 true. `safety_logs.has_vest` |
| `confidence` | 0~1 | 판정 근거가 된 검출 중 가장 높은 점수. `safety_logs.confidence` |
| `persons` | 정수 | 찾은 사람 수 |
| `detections` | 배열 | 점수 기준(`CONF_THRES`)을 넘은 검출. `box`는 원본 사진 기준 픽셀 `[x1, y1, x2, y2]`. 로그·디버깅용 |
| `image` | `{width, height}` | 받은 사진 크기 |
| `model` | 문자열 | 쓴 모델 파일 이름 |
| `infer_ms` | 정수 | 전처리부터 판정까지 걸린 시간 |

### 판정 규칙

1. 모델의 클래스 이름으로 검출을 나눈다: 사람, 안전모 착용, 안전모 미착용(`NO-` 클래스), 조끼 착용, 조끼 미착용.
2. 안전모 미착용 검출이 있거나, 안전모 착용 검출 수가 사람 수보다 적으면 `has_helmet: false`. 조끼도 같은 방식.
3. 사람도, 안전모·조끼 관련 검출도 없으면 `verdict: "no_person"` (ESP32는 사람을 봤지만 모델이 못 찾은 경우). gateway는 `pass`처럼 로그만 남긴다.
4. 그 밖에는 `has_helmet`과 `has_vest`가 둘 다 true면 `pass`, 아니면 `fail`.

## 오류

| 코드 | 언제 | gateway가 할 일 |
|---|---|---|
| 400 | 본문이 비었거나 JPEG로 읽을 수 없음 | 버리고 로그 |
| 413 | 2MB 초과 | 버리고 로그 |
| 503 | 모델 파일이 없거나 불러오지 못함 | 버리고 로그 (재시도해도 같다) |

오류 본문은 `{"detail": "<이유>"}`.

## 상태 확인

`GET /health` → 200 `{"service": "inference", "status": "ok", "model_loaded": true, "model": "ppe_yolov8.onnx", "classes": ["Hardhat", "NO-Hardhat", …]}`

모델이 없어도 200을 준다 (`model_loaded: false`). 그래야 모델 없이도 compose가 뜨고 CI가 돈다. 모델이 필요한 판정은 503으로 알린다.

## 설정 (환경 변수)

| 이름 | 기본값 | 뜻 |
|---|---|---|
| `MODEL_PATH` | `/models/ppe_yolov8.onnx` | 모델 파일 (`pi/models/`를 읽기 전용으로 마운트) |
| `CONF_THRES` | `0.4` | 이 점수 미만 검출은 버린다 |
| `IOU_THRES` | `0.45` | 겹친 상자 하나로 합치는 기준 (NMS) |
| `ORT_THREADS` | `3` | onnxruntime 스레드 수 (Pi 5는 4코어, gateway·uploader 몫 1코어) |

## 정한 것 (명수)

- [x] `no_person`은 pass처럼 로그와 gateway `/recent`에만 남기고 uploader로 넘기지 않는다.
- [x] gateway의 inference 호출 제한 시간은 **10초** (`INFERENCE_TIMEOUT`, 잠정). 넘으면 그 사진은 `verdict: error`로 버린다. Pi 5 실측 추론 시간이 나오면 다시 정한다.
