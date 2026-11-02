# pi/inference — 안전모·조끼 판정

- 담당: 우진
- 주소: `http://inference:8003` (compose 내부망만. 테스트할 때는 `docker-compose.ci.yml`이 8003을 연다)
- 형식: [docs/contracts/inference.md](../../docs/contracts/inference.md)

| 주소 | 하는 일 |
|---|---|
| `POST /predict` | 본문 JPEG → 판정 JSON (`verdict`, `has_helmet`, `has_vest`, `confidence`, `persons`, `detections`, `infer_ms`) |
| `GET /health` | 모델이 없어도 200. `model_loaded`, `classes`, `error`로 상태를 알린다 |

## 판정

1. 사진을 비율을 지켜 640×640에 맞추고(남는 곳은 회색) YOLOv8 PPE ONNX를 돌린다.
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

`MODEL_PATH`(기본 `/models/ppe_yolov8.onnx`), `CONF_THRES`(0.4), `IOU_THRES`(0.45), `ORT_THREADS`(3). 모델은 시작 때 한 번만 불러오고, 판정은 한 번에 한 장씩 한다 (Pi 5 4GB, uvicorn worker 1개).

## 테스트

```bash
cd pi && docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build --wait inference
cd .. && pytest tests/pi/inference
```

- `test_predict_input.py`: 오류 코드 (모델 없이도 돈다)
- `test_predict_contract.py`: 응답 형식과 사진별 판정 (`@pytest.mark.model`, `pi/models/ppe_yolov8.onnx`가 있을 때만)
- 사진을 더하려면 `tests/fixtures/images/`에 넣고 `tests/pi/inference/expected.json`에 기대 판정을 한 줄 적는다. 안전모·조끼를 착용한 사진, 안 한 사진이 하나씩은 있어야 판정을 제대로 확인할 수 있다.
