# 모델 후보 검증 — 2026-11-02

기존 `Hansung-Cho/yolov8-ppe-detection` 후보를 ONNX로 바꿔 검증하던 중, 안전모·조끼를 착용한 사진을 위반으로 판정하는 회귀 사례를 발견했다. 정답 라벨을 바꾸지 않고 원본 PyTorch 결과를 확인했으며 같은 오탐이 재현됐다. `Hardhat` 점수는 약 0.224로 기본 임계값 0.4보다 낮았고 조끼를 찾지 못했다.

## 동일 사진 비교

사진은 원본 라벨과 육안 확인으로 모델 실행 전에 선정했다. 입력 640×640, confidence 0.4, IoU 0.45로 비교했다. 아래는 세 사진의 판정 일치 여부이며 정확도 벤치마크가 아니다.

| 후보 | 착용 `test_11` | 둘 다 미착용 `test_0` | 조끼 미착용 `test_26` | 판단 |
|---|---|---|---|---|
| [Hansung YOLOv8n](https://huggingface.co/Hansung-Cho/yolov8-ppe-detection) | 실패: 안전모·조끼를 놓침 | 일치 | 일치 | 원본·변환본 수치는 일치하지만 이 회귀 사례를 통과하지 못함 |
| [baskarmother YOLOv8n](https://huggingface.co/baskarmother/yolov8-ppe-construction) | 실패: 조끼를 놓침 | 일치 | 일치 | 작은 모델 대안도 같은 착용 사례를 통과하지 못함 |
| [SafeSight YOLOv8s](https://huggingface.co/killuminati1/construction-ppe-yolov8) | 일치 | 일치 | 일치 | `model-v1` 통합 검증 후보로 제공 |

SafeSight는 원본과 ONNX 모두 비교했다. HTTP에서 위 세 사진과 공통 `blank.jpg`의 판정·응답 계약을 검증했다. 원본 데이터의 학습 중복 여부는 확인하지 않았으므로 독립 테스트셋 성능으로 해석하지 않는다. 눈에 가려진 착용 사진의 조끼 점수는 약 0.403으로 임계값에 가까워 장비별 회귀 검사가 필요하다.

비교에 쓴 원본을 다시 확인할 수 있는 값:

| 후보 | revision | best.pt SHA256 |
|---|---|---|
| Hansung | `ac0027bd38bc619d5ce4f52b4cc01beb87d8b958` | `2419700bbe3b8d38f9000655d9cf952a4bc93ef6c143baf8b49a0abde5d0760f` |
| baskarmother | `3213ed51de90cbc76e577e6944e84f7c74343526` | `8714b4b2bbde95b3a07dcdbe873995e34742b5ce628464a4da232721d4691ffe` |
| SafeSight | `06ce70134a78f31881e2f9a223719d60a0a9a6a9` | `31ef3ca04a17cf545f3fcfc64c4af8993a41d52ccc460e82aff01d5354603533` |

## 변환·서버 검사

- Python 3.12.10, CPU, `requirements-export.txt`의 고정 버전으로 FP32 opset 17을 내보냈다.
- ONNX checker와 CPU 실행, 클래스·입출력 형태, 유한한 출력값과 점수 0~1을 확인했다.
- 영 입력과 고정 난수 입력으로 PyTorch와 ONNX의 출력 전체를 `rtol=atol=0.001` 조건에서 비교했다. 최대 절대오차가 0.001보다 커도 상대 허용오차를 포함한 `abs(a-b) <= atol + rtol*abs(b)`를 만족해야 통과한다. 수치는 `model-v1.json`에 기록했다.
- 잘못된 직사각형 입력, 전치 출력, FP16 입력, 비연속 클래스 번호, 조끼 클래스 누락 모델은 HTTP에서 `/health` 200, `model_loaded: false`, `/predict` 503으로 거부했다. 정상 형식의 소형 검증 그래프는 200을 반환했다.

## 남은 현장 확인

SafeSight ONNX는 42.7 MiB로 기존 후보의 약 11.7 MiB보다 크다. Pi의 1GB inference 컨테이너 제한 안에서 기동·추론되는지 arm64 CI로 확인하고, Pi 5 실물의 메모리와 추론 시간은 명수가 커밋·모델 SHA256을 함께 기록해 측정해야 한다. PC 결과를 Pi 측정값으로 쓰지 않는다.

현장 사진의 조명·거리·가림·복수 작업자 사례와 ESP32 연결 검증, 계약 초안의 명수 확인은 아직 필요하다. 현장 모델 확정 및 공용 `docs/decisions.md` 반영은 담당자 합의 뒤 진행한다. 이번 작업은 우진 담당 폴더의 검증 후보와 재현 자료만 제공한다.
