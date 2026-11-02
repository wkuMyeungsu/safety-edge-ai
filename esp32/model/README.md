# Edge Impulse 사람 감지 모델

| 항목 | 값 |
|---|---|
| Edge Impulse 프로젝트 | https://studio.edgeimpulse.com/public/121370/latest (사용 여부 미정) |
| 배포 형식 | Arduino library |
| 모델 종류 | 물체 감지 FOMO, 라벨 `hum` 하나 (사람). 모델 자체 threshold 0.5 |
| 입력 크기 | 64×64 RGB, resize mode fit longest (화면 전체를 줄이고 위아래를 검게 채움), int8, EON |
| 라이브러리 | `Person_detection_FOMO_3_inferencing` 1.0.6 (`#include <Person_detection_FOMO_3_inferencing.h>`) |
| 학습 데이터 | 1.0.6: 사람이 없는 배경 이미지를 추가해 다시 학습 (1.0.5에서 사람이 없는데 감지되는 오탐이 있었다) |

## 받는 법

1. Edge Impulse 프로젝트에서 Deployment → Arduino library로 내려받는다.
2. 받은 zip을 이 폴더(`esp32/model/`)에 넣고 커밋한다. CI는 이 폴더의 `*.zip`을 설치해 펌웨어와 함께 컴파일하고, zip이 그대로면 컴파일 결과를 캐시에서 쓴다.
3. 내 PC에서는 Arduino IDE의 Sketch → Include Library → Add .ZIP Library로 같은 zip을 추가한다.
4. 위 표의 입력 크기와 버전 칸을 채운다.
