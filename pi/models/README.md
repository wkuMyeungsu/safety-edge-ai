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

## 선택적 속도 최적화 후보: 576 입력

[model-v1-576](https://github.com/wkuMyeungsu/safety-edge-ai/releases/tag/model-v1-576)은 기존 SafeSight 원본 가중치를 **576×576 FP32, opset 17**로 다시 내보낸 후보이다. 640 배포본과 `model-v1`은 보존한다. 서버는 모델의 정적 입력 크기를 읽으므로 추론 코드·판정 임계값·기대 정답 변경 없이 사용할 수 있다. 모델 파일만 자동으로 교체하지는 않는다.

- 메타데이터: [model-v1-576.json](model-v1-576.json)
- SHA256: `85533d8ef50e65435e5b7d9dfb7d87f5f0aa604469ffe222a471ae17648bd2f2`
- 입력 `[1, 3, 576, 576]`, 출력 `[1, 23, 6804]`, 44,715,015 bytes. 입력 픽셀 수는 19% 줄지만 가중치 파일 크기는 거의 같다.
- 원본 PyTorch 대비 영 입력·고정 난수 입력 수치 비교 통과(`rtol=atol=0.001`). 576 모델의 실제 HTTP 테스트는 20개 통과, 1개 건너뜀(모델 없음 503 검사)이다.

```bash
mkdir -p pi/models/optimized-576
curl -fL https://github.com/wkuMyeungsu/safety-edge-ai/releases/download/model-v1-576/ppe_yolov8.onnx \
  -o pi/models/optimized-576/ppe_yolov8.onnx
python pi/models/verify_onnx.py pi/models/optimized-576/ppe_yolov8.onnx \
  --sha256 85533d8ef50e65435e5b7d9dfb7d87f5f0aa604469ffe222a471ae17648bd2f2
```

재변환 명령은 `export_onnx.py --source safesight --weights <검증한 원본.pt> --imgsz 576 --output <새 파일.onnx>`이다. Windows PC에서 같은 3개 스레드·spinning 활성 상태로 크기를 순차 비교한 [원본 결과](reports/input-size-comparison-2026-11-02-pc.json)는 다음과 같다. 코드 커밋은 `b0db731824cd6caed747ed42e39194a4c876fa4b`, 사진 4종 각각 예열 1회와 측정 3회다.

| 입력 | 기존 사진 기대 판정 | 추론 중앙값 (Windows PC) |
|---|---|---|
| 640 | 모두 일치 | 201 ms |
| 608 | 모두 일치 | 194 ms |
| 576 | 모두 일치 — 선택 | 180.5 ms |
| 544 | 착용 사진의 조끼 누락 — 제외 | 153 ms |
| 512·448·384·320 | 같은 착용 사진 판정 실패 — 제외 | 별도 초기 비교 원본에 기록 |

576은 검사한 크기 중 가장 작은 통과 후보이며 이 PC 비교에서 중앙값이 약 10.2% 줄었다. 사진의 `pass`/`fail`/`no_person` 및 안전모·조끼 판정은 유지되지만 검출 점수·좌표·부가 클래스는 달라질 수 있다. 사진 4종의 회귀 검사는 전체 현장 정확도의 동등성을 보장하지 않으며, 실제 Pi 속도·정확도 검증은 별도다. 기존 CI는 계속 `model-v1` 640 모델을 사용한다.

576 컨테이너 측정에는 아래 도구의 `--model pi/models/optimized-576/ppe_yolov8.onnx --manifest pi/models/model-v1-576.json`을 지정한다. 런타임 기본값 `ORT_THREADS=3`, `ORT_SPINNING=1`은 유지한다.

### ARM64 QEMU에서 640과 576 비교

공개 Release에서 다운로드한 파일의 SHA256을 확인하고 실행했다. [576 원본 결과](reports/arm64-qemu-576-2026-11-02.json)의 코드 커밋은 `ff295b6fc44e0f85f8b1dffc809e5d30f594ad6b`이다. [기존 640 측정](reports/arm64-qemu-2026-11-02.json)과 같은 호스트·QEMU·Python·패키지 버전, CPU quota 3, ORT 스레드 3, spinning 활성, 메모리 1 GiB, swap 0 조건이다. 각 실행은 사진별 예열 1회 + 측정 5회(20회), 동시 요청 2건을 수행했다.

| 항목 | 기존 640 | 최적화 후보 576 |
|---|---:|---:|
| 서버 추론 중앙값 | 26,335 ms | 20,997.5 ms |
| 서버 추론 P95 | 26,955 ms | 21,302 ms |
| 서버 추론 최대 | 27,052 ms | 21,359 ms |
| HTTP 왕복 중앙값 | 26,399.622 ms | 21,039.283 ms |
| cgroup 최대 메모리 | 304,185,344 bytes (290.094 MiB) | 374,820,864 bytes (357.457 MiB) |
| OOM / OOM kill | 0 / 0 | 0 / 0 |
| 동시 요청 중 상태 응답 | 2개 대기, 6.838 ms | 2개 대기, 7.501 ms |
| 측정·예열·동시 요청 기대 판정 | 모두 일치 | 모두 일치 |

중앙값은 약 **20.3% 감소**했다. 사진별 예열 응답의 `verdict`, `has_helmet`, `has_vest`, `persons`도 기존 640 결과와 직접 대조해 모두 일치했다. 점수와 좌표는 해상도에 따라 달라지므로 동일하다고 주장하지 않는다.

속도 개선과 함께 **이번 cgroup 최대 메모리는 67.363 MiB 증가**했다. 두 값 모두 컨테이너 전체 생명주기의 메모리이며 QEMU·모델 로드·해시 확인·계측 비용을 포함한다. 순수 ONNX 메모리나 실물 Pi의 메모리로 해석하지 않는다. 두 모델 모두 1 GiB 제한 내에서 완료됐다. 이 수치는 QEMU 가상 실행 결과이며 Pi 5 속도로 환산할 수 없다.

576 재현 명령(현재 커밋 라벨로 ARM64 이미지를 빌드한 뒤):

```bash
python3 pi/models/run_container_benchmark.py \
  --image safety-edge-ai/inference:arm64-benchmark \
  --model pi/models/optimized-576/ppe_yolov8.onnx \
  --manifest pi/models/model-v1-576.json \
  --server-label "실제 호스트 CPU / OS / QEMU 버전" \
  --ort-threads 3 --ort-spinning 1 --repeats 5 --parallel 2 \
  --output arm64-576-result.json
```

## 이전 Hansung 후보 재현

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
- `--imgsz`는 320~640 사이의 32 배수이며 기본값은 640이다. 작은 입력도 별도 파일로 내보내며 PyTorch/ONNX 수치 비교는 지정한 크기로 수행한다. 사진별 기대 판정 검사를 통과하기 전에는 배포 후보로 선택하지 않는다.
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

## 실물 없이 ARM64 컨테이너에서 측정

PC의 런타임 설정은 `compare_runtime.py --server-label "실제 PC CPU와 OS" --output runtime-comparison.json`으로 비교할 수 있다. 추론 의존성이 설치된 Python으로 실행하며, 스레드 1·2·3개와 spinning 0·1의 서버 6개를 한 번에 하나씩 실행한다. 모든 측정의 기대 판정과 각 사진 예열 응답의 점수·좌표·인원 수까지 대조한다. [초기 PC 비교](reports/runtime-comparison-2026-11-02-pc.json)에서 판정은 동일했으며, 대기 방식 변경의 일관된 이득을 확인하지 못해 기본 `ORT_THREADS=3`, `ORT_SPINNING=1`을 유지했다. 이 기록은 일부 캐시 빌드가 겹친 초기 스크리닝으로 정밀한 설정별 순위를 뜻하지 않는다.

`run_container_benchmark.py`는 실제 ONNX 서버를 Linux ARM64 컨테이너에서 실행한다. x86 PC에서는 QEMU/binfmt가 준비된 Docker가 필요하다. Windows에서는 WSL 내부에서 Linux Docker Engine과 이 도구를 함께 실행할 수도 있다. 컨테이너는 Pi Compose와 같은 메모리 1 GiB, ORT 스레드 3개를 사용하며 CPU quota 3개, swap 0으로 제한한다. 이 CPU quota는 Pi 5의 코어 성능이나 클럭을 재현하지 않는다.

추론 코드와 측정 도구를 커밋한 뒤 저장소 루트에서 실행한다. Python은 표준 라이브러리만 필요하다. Docker CLI가 로컬 Linux 엔진에 연결되어 있어야 하며 cgroup v2를 사용한다.

```bash
docker build --platform linux/arm64 \
  --label org.opencontainers.image.revision="$(git rev-parse HEAD)" \
  -t safety-edge-ai/inference:arm64-benchmark pi/inference
python3 pi/models/run_container_benchmark.py \
  --image safety-edge-ai/inference:arm64-benchmark \
  --server-label "실제 호스트 CPU / OS / QEMU 버전" \
  --repeats 5 --parallel 2 --output arm64-benchmark.json
```

- 이미지의 아키텍처·커밋 라벨과 컨테이너 내부 Python 코드·requirements·ONNX의 SHA256을 확인한다. 기존 HTTP 판정 검사를 재사용하며, 기본 20회 측정과 사진별 예열 4회, 동시 요청 2회를 실행한다.
- 스레드 비교에는 `--ort-threads 1|2|3`, 대기 방식 비교에는 `--ort-spinning 0|1`을 사용한다. spinning을 생략하면 서버 기본값을 따른다. CPU quota는 모든 비교에서 3으로 유지하며 실제 지정값을 보고서에 기록한다.
- 포트는 `127.0.0.1`에 임의 배정한다. 다른 서비스는 실행하지 않으며, 도구가 만든 컨테이너만 종료·제거한다. 이미지와 출력 보고서는 보관한다.
- `memory.current`와 `memory.peak`는 cgroup 전체 사용량이다. peak는 모델 로드와 계측 보조 프로세스까지 포함하며, QEMU 환경에서는 에뮬레이터 비용도 포함한다. 모델 파일 크기나 순수 ONNX 메모리와는 다르다. OOM 발생과 메모리·swap 제한도 검사한다.
- QEMU 결과는 ARM64 실행 호환성과 제한된 메모리에서의 동작을 확인하는 값이다. **실제 Pi 5의 추론 속도·메모리로 보고하거나 환산하지 않는다.** 실물 측정과 ESP32 연결 검증은 여전히 별도다.

### 2026-11-02 가상 실행 결과

[원본 JSON](reports/arm64-qemu-2026-11-02.json)은 커밋 `a79b64bc2d9b6cf62605cc91f058ba6f2d9e59f6`을 Intel Core Ultra 7 258V의 Windows 11 → WSL2 Ubuntu 26.04 → QEMU aarch64 10.2.1 → Linux ARM64 컨테이너에서 실제 실행한 기록이다. Python 3.12.16, ONNX Runtime 1.20.1이며 컨테이너 내부 ONNX SHA256은 위 배포본과 일치했다.

| 측정 항목 | 결과 |
|---|---|
| 자원 제한 | 메모리 1 GiB, swap 0, CPU quota 3, ORT 스레드 3 |
| 입력·횟수 | 빈 화면과 실제 사진 3장, 사진별 예열 1회 + 측정 5회 (측정 20회) |
| 기대 판정 | 20회 모두 일치; 예열 4회와 추가 동시 요청 2건도 일치 |
| 서버 추론 중앙값 / P95 / 최대 | 26,335 / 26,955 / 27,052 ms |
| HTTP 왕복 중앙값 / P95 / 최대 | 26,399.622 / 26,971.434 / 27,067.687 ms |
| cgroup 현재 사용량 (측정 후) | 303,579,136 bytes (289.516 MiB) |
| cgroup 최대 사용량 (컨테이너 전체 생명주기) | 304,185,344 bytes (290.094 MiB) |
| 메모리 부족 | `oom=0`, `oom_kill=0`, swap 한도 0 확인 |
| 동시 요청 중 `/health` | 2건 대기 중 6.838 ms, 두 판정 모두 일치 |

서버 추론 시간은 전처리·ONNX 실행·후처리·판정을 포함한다. JPEG 디코딩과 요청 대기는 HTTP 왕복 시간에만 포함된다. P95는 측정 20개의 nearest-rank 값이다. 메모리 최대값에는 QEMU와 모델 로드·해시 검사·계측 과정도 포함된다. **26초라는 시간은 이 PC의 에뮬레이션 결과이며 Pi 5 성능이나 현장 정확도 검증 결과가 아니다.**

검증 과정에서 커밋 라벨 없는 이미지가 거부되고 성공 보고서가 생성되지 않는 것도 확인했다. 측정 후 전용 컨테이너는 자동 제거했으며, 재실행용 이미지는 남겨 두었다. 같은 코드의 ARM64 CI는 [run 41394841318](https://github.com/wkuMyeungsu/safety-edge-ai/actions/runs/41394841318)에서 58개 통과, 1개 건너뜀(모델 없는 경우의 503 검사)을 기록했다.

## 실제 Pi 원격 연결·판정 확인 (2026-11-02)

[원본 결과](reports/pi-gateway-smoke-2026-11-02.json)는 `deploy-pi`로 코드 `5bac24068f0cb2aa53015bcad6f8375627e302e7`을 실제 Pi에 배포하고, Tailscale Funnel의 `/frame`과 `/recent`로 사진 4종을 각각 한 번 확인한 기록이다. 배포 로그의 모델 입력은 **640×640**이었다. 배포는 Git 밖의 모델 파일을 교체하지 않으므로 **576 최적화 모델의 실물 비교 결과가 아니다.**

| 사진 | 실제 판정 | Pi가 반환한 `infer_ms` | uploader |
|---|---|---:|---|
| `blank.jpg` | `no_person` | 459 | 호출 없음 |
| `test_11.jpg` | `pass` (둘 다 착용) | 447 | 호출 없음 |
| `test_0.jpg` | `fail` (둘 다 미착용) | 463 | `stored` |
| `test_26.jpg` | `fail` (조끼 미착용) | 444 | `stored` |

네 기대 판정이 모두 일치했고 대기 줄은 시험 후 0이었다. 위 시간은 서버의 전처리·추론·후처리 시간이며 인터넷 왕복·결과 조회 시간을 포함하지 않는다. 예열·반복 없이 사진마다 한 번 보낸 연결 검사이므로 정식 성능 벤치마크로 해석하지 않는다.

현재 gateway API와 `deploy-pi status`에는 ONNX SHA256과 메모리 측정값이 없어 이를 확인하지 못했다. 파일명·640 입력·PPE 클래스 매핑은 시작 로그에서 확인했지만, 모델 파일 동일성과 576 적용·메모리 실측은 Pi 담당자의 확인이 필요하다.

- [배포 성공](https://github.com/wkuMyeungsu/safety-edge-ai/actions/runs/41400753480), [시험 잠금 해제 성공](https://github.com/wkuMyeungsu/safety-edge-ai/actions/runs/41401068822). 로그에서 시험 중 표시가 없음을 확인했다.
- 시험 장치 ID는 `test-woojin-20261102-063509`이며 위반 시험 기록 2건은 Supabase `log_id=8,9`로 남아 있다. 공개 API에 삭제 기능이 없어 삭제하지 않았다. 이 장치 ID로 식별할 수 있다.
- 인증 토큰은 요청 헤더에만 사용했으며 보고서·코드·로그에 저장하지 않았다.
