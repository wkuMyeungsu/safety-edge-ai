# pi/inference — 안전모·조끼 판정

- 담당: 우진
- 주소: `http://inference:8003` (compose 내부망만. 테스트할 때는 `docker-compose.ci.yml`이 8003을 연다)
- 형식: [docs/contracts/inference.md](../../docs/contracts/inference.md)

| 주소 | 하는 일 |
|---|---|
| `POST /predict` | 본문 JPEG → 판정 JSON (`verdict`, `has_helmet`, `has_vest`, `confidence`, `persons`, `detections`, `infer_ms`) |
| `GET /health` | 모델이 없어도 200. `model_loaded`, `classes`, `error`로 상태를 알린다 |

## 판정

1. 사진을 비율을 지켜 모델의 정적 입력 크기(기존 640×640, 최적화 후보 576×576)에 맞추고 남는 곳은 회색으로 채운 뒤 YOLOv8 PPE ONNX를 돌린다.
2. 점수가 `CONF_THRES` 이상인 검출만 남기고, 클래스별 NMS(`IOU_THRES`)로 겹친 상자를 합친다.
3. 클래스 이름으로 종류를 나눈다 (`detector.py`의 `CATEGORY_NAMES`). 대소문자·기호는 무시한다.

   | 종류 | 이름 |
   |---|---|
   | 사람 | Person, Worker |
   | 안전모 착용 / 미착용 | Hardhat, Helmet / NO-Hardhat, NO-Helmet, Head |
   | 조끼 착용 / 미착용 | Safety Vest, Vest / NO-Safety Vest, NO-Vest |

4. 미착용 검출이 있거나 착용 검출 수가 사람 수보다 적으면 그 장비는 false. 사람 검출을 놓쳐도 안전모·조끼 검출 수로 사람 수를 짐작한다 (`persons`).
5. 사람이 없으면 `no_person`, 둘 다 true면 `pass`, 아니면 `fail`.

안전모나 조끼 클래스가 없는 모델은 불러오지 않는다 (`/health`의 `error`에 이유, `/predict`는 503).
입력은 float32 `[1, 3, S, S]`, 출력은 NMS 전 float32 `[1, 4+클래스 수, N]`인 고정 크기 모델만 받는다. 다른 형식은 시작할 때 거부한다. 변환과 검증 방법은 [모델 문서](../models/README.md).

## 설정

`MODEL_PATH`(기본 `/models/ppe_yolov8.onnx`), `CONF_THRES`(0.4), `IOU_THRES`(0.45), `ORT_THREADS`(3), `ORT_SPINNING`(1). 모델은 시작 때 한 번만 불러오고, 판정은 한 번에 한 장씩 한다 (Pi 5 4GB, uvicorn worker 1개).

`ORT_SPINNING=0`이면 ONNX Runtime 작업 스레드가 대기할 때 CPU를 계속 점유하는 spinning을 끈다. `1`이면 켠다. 가중치·입력 크기·판정 임계값은 바뀌지 않는다. CPU quota와 아키텍처에 따라 효과가 다르므로 같은 사진으로 비교한다. [ONNX Runtime 스레드 설정](https://onnxruntime.ai/docs/performance/tune-performance/threading.html).

요청은 비동기로 순서를 기다린 뒤 JPEG 디코딩·전처리·추론·판정을 한 장씩 처리한다. 기다리는 동안 작업 스레드를 점유하지 않으며 `/health`는 추론과 별도로 응답한다. JPEG가 아닌 이미지와 2MB를 넘는 본문은 거부하고, 긴 비율의 JPEG도 축소 후 변 길이가 최소 1픽셀이 되도록 처리한다.

## 테스트

```bash
cd pi && docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build --wait inference
cd .. && pytest tests/pi/inference
```

- `test_predict_input.py`: 오류 코드 (모델 없이도 돈다)
- `test_predict_contract.py`: 응답 형식과 사진별 판정 (`@pytest.mark.model`, `pi/models/ppe_yolov8.onnx`가 있을 때만)
- `test_predict_concurrency.py`: 실제 모델에 48개 요청을 보내는 동안 상태 확인과 모든 응답을 검사한다.
- 실제 사진은 `tests/pi/inference/images/`, 공통 빈 화면은 `tests/fixtures/images/`에서 읽는다. 출처·라이선스·기대 판정 근거는 [사진 문서](../../tests/pi/inference/images/README.md)에 기록한다.
- `expected.json`은 착용, 두 장비 미착용, 조끼 미착용, 사람 없음 4가지를 검사한다. 기대값을 모델 출력에 맞춰 바꾸지 않는다.
