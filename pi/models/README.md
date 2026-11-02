# 모델 변환·검증

담당: 우진. `*.onnx`, `*.pt`는 Git에 커밋하지 않는다. 변환은 **PC에서만** 하고 Pi에는 ONNX Runtime만 설치한다.

## 검증용 배포 후보

`model-v1`은 [SafeSight PPE](https://huggingface.co/killuminati1/construction-ppe-yolov8)를 변환한 **통합 테스트용 프리릴리스**다. 현장 채택을 확정하는 배포가 아니다. 기존 후보는 착용 사진을 위반으로 판정해 대안 2개와 비교했다. [비교 결과와 남은 검증](validation.md), [변환 결과 JSON](model-v1.json)을 함께 확인한다.

| 항목 | 고정값 |
|---|---|
| 원본 | `killuminati1/construction-ppe-yolov8`, `best.pt`, YOLOv8s, 19클래스 |
| 원본 revision | `06ce70134a78f31881e2f9a223719d60a0a9a6a9` |
| 원본 SHA256 | `31ef3ca04a17cf545f3fcfc64c4af8993a41d52ccc460e82aff01d5354603533` |
| 배포 파일 | `ppe_yolov8.onnx`, 44,746,935 bytes (42.7 MiB) |
| 배포 SHA256 | `0471240ce41e89bc0e58daf0b12d33102d6a70db5bad611f90533f6d3402cb17` |
| 입출력 | `[1, 3, 640, 640]` → `[1, 23, 8400]`, FP32, opset 17, NMS 제외 |
| 원본 Model Card 라이선스 표시 | Apache-2.0. Ultralytics 코드와 원본 데이터의 별도 조건은 [원본 Model Card](https://huggingface.co/killuminati1/construction-ppe-yolov8)를 확인한다 |

```bash
curl -fL https://github.com/wkuMyeungsu/safety-edge-ai/releases/download/model-v1/ppe_yolov8.onnx -o pi/models/ppe_yolov8.onnx
python pi/models/verify_onnx.py pi/models/ppe_yolov8.onnx --sha256 0471240ce41e89bc0e58daf0b12d33102d6a70db5bad611f90533f6d3402cb17
```

## 기존 후보 재현

기존 문서의 [Hansung-Cho/yolov8-ppe-detection](https://huggingface.co/Hansung-Cho/yolov8-ppe-detection)을 같은 가중치로 검증한다. 현장 모델 채택과 Pi 성능 측정은 별도다.

| 항목 | 고정값 |
|---|---|
| 파일 | `best.pt` (YOLOv8n PPE, 10클래스) |
| 원본 revision | `ac0027bd38bc619d5ce4f52b4cc01beb87d8b958` |
| 원본 SHA256 | `2419700bbe3b8d38f9000655d9cf952a4bc93ef6c143baf8b49a0abde5d0760f` |
| 출력 | `ppe_yolov8.onnx`, FP32, opset 17 |
| 입출력 | `[1, 3, 640, 640]` → `[1, 14, 8400]`, NMS 제외 |

원본 Model Card의 라이선스 표시는 MIT이고 체크포인트 내장 메타데이터는 AGPL-3.0이다. 두 출처의 표시를 그대로 기록하며, 이 저장소가 원본 가중치에 새 라이선스를 부여하지 않는다. Ultralytics 코드의 라이선스는 [원본 저장소](https://github.com/ultralytics/ultralytics/blob/v8.3.232/LICENSE)를 따른다.

## PC에서 변환

Python 3.12 가상환경에 [requirements-export.txt](requirements-export.txt)를 설치한다. 서버 환경과 분리한다. 아래는 저장소 루트 기준이다.

```bash
python3.12 -m venv pi/models/.venv
pi/models/.venv/bin/python -m pip install -r pi/models/requirements-export.txt
pi/models/.venv/bin/python pi/models/export_onnx.py --source safesight --download
```

Windows PowerShell에서는 `python3.12` 대신 `py -3.12`, `pi/models/.venv/bin/python` 대신 `.\pi\models\.venv\Scripts\python.exe`를 쓴다.

- `--source safesight`가 검증용 배포 후보다. 기존 후보는 `--source hansung`으로 재현한다. 생략 시 기존 동작대로 hansung을 사용한다.
- 이미 받은 동일 원본은 `--weights <best.pt 경로>`로 지정한다. 선택한 `--source`의 해시와 맞아야 하며 `--download`와 함께 쓰지 않는다.
- 원본 해시를 확인한 뒤 가중치를 불러온다. 정적 크기, 배치 1, FP32, NMS 제외, simplify 제외로 변환한다.
- ONNX checker, 서버와 같은 클래스·입출력 검사, CPU 실행, NaN·점수 범위 검사, PyTorch 대비 출력 비교(영 입력·고정 난수 입력, `rtol=atol=0.001`)가 모두 통과해야 출력 파일을 만든다.
- 기존 출력은 덮어쓰지 않는다. 비교할 변환본은 `--output`으로 다른 경로를 지정한다.
- 변환 과정의 JSON 출력에 원본/결과 SHA256, 패키지 버전, 수치 비교 결과가 들어 있다. ONNX 내보내기 시각 메타데이터 때문에 재변환 파일의 해시는 달라질 수 있다. 배포본은 배포 당시 해시로 확인한다.

## 독립 검증

`verify_onnx.py`는 torch·ultralytics 없이 `pi/inference/requirements.txt`만으로 실행할 수 있다. 서버와 동일한 형식 검사 후 실제 CPU 추론을 한 번 실행한다.

```bash
python pi/models/verify_onnx.py pi/models/ppe_yolov8.onnx
python pi/models/verify_onnx.py pi/models/ppe_yolov8.onnx --sha256 <배포본-SHA256>
```

해시 불일치, 클래스 누락, 잘못된 입출력, 실행 실패는 종료 코드 1이다. 서버도 지원하지 않는 모델을 시작할 때 거부하고 `/health`에 원인을 기록한다.

## 배포와 판정 확인

검증한 ONNX는 GitHub Release `model-v1`에 `ppe_yolov8.onnx` 이름으로 첨부한다. CI는 Release를 내려받아 `@pytest.mark.model` 테스트에 쓰고 이 README 내용이 바뀌면 캐시를 갱신한다. 새 모델은 기존 배포본을 덮어쓰지 말고 버전과 README를 함께 갱신한다.

```bash
cd pi
docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build --wait inference
cd ..
python -m pytest tests/pi/inference
```

입출력 호환성·수치 일치는 사진별 정확도를 보장하지 않는다. 실제 사진 검사는 HTTP 테스트에서 수행한다. Pi 5의 추론 시간·메모리·ESP32 연결 검증은 실물을 가진 명수 담당이며, 측정 시 커밋과 모델 SHA256을 함께 기록한다.

실제 회귀 사진의 원본 라벨·라이선스·해시는 [tests/pi/inference/images/README.md](../../tests/pi/inference/images/README.md)에 있다. `expected.json`의 착용·미착용 기대값은 모델 출력과 별개로 유지한다.

## 실제 서버 반복 실행

서버를 최신 커밋과 검증한 `MODEL_PATH`로 다시 시작한 뒤, 표준 라이브러리만 사용하는 도구로 실제 `/predict`를 반복 호출한다. 모델이 없는 서버, 해시·클래스 불일치, 기대 판정 불일치는 실패로 처리한다.

```bash
python pi/models/run_http_smoke.py --url http://127.0.0.1:8003 \
  --server-label "실제로 서버를 실행한 장비와 OS" \
  --repeats 10 --parallel 48 --output smoke-result.json
```

- 사진마다 한 번 예열 후 10회씩 측정한다. 기본 사진 4종이면 40회다. 추가로 동시 요청 48개와 `/health` 응답을 확인한다.
- 보고서에는 코드 커밋, 로컬 모델 SHA256, 원본 판정 JSON, 개별 측정값, 중앙값·P95·최댓값이 들어 있다. HTTP 시간은 전체 왕복 시간, `infer_ms`는 서버 전처리부터 판정까지의 시간이다. 비동기 대기 시간과 JPEG 디코딩 시간은 `infer_ms`에 포함하지 않는다.
- `/health`는 서버 파일 해시를 제공하지 않는다. 도구는 이름·클래스와 로컬 파일 해시만 대조하므로 서버의 `MODEL_PATH`가 해당 파일인지 직접 확인해야 한다.
- [2026-11-02 PC 실행 결과](reports/http-smoke-2026-11-02-pc.json): 40회 기대 판정 일치, 추론 중앙값 176.5ms/P95 301ms, 48개 동시 요청 중 상태 응답 3.766ms. 이 값은 Windows PC 결과이며 Pi 성능이나 현장 정확도 평가가 아니다.
