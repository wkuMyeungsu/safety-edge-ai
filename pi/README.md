# pi

라즈베리 파이 5에서 Docker로 실행하는 3개 서비스. Pi 실물은 명수가 가지고 있다.

| 폴더 | 서비스 | 포트 | 하는 일 | 담당 |
|---|---|---|---|---|
| `gateway/` | gateway | 8001 (외부 공개) | esp32 사진 수신, 대기 줄, inference → uploader 호출 순서 | 명수 |
| `inference/` | inference | 8003 (내부) | PPE 모델로 안전모·조끼 판별 | 우진 |
| `uploader/` | uploader | 8004 (내부) | Supabase 기록·사진 저장, 실패 시 재시도 | 도은 (cloud) |
| `models/` | (볼륨) | | 모델 파일 위치. `*.onnx`는 커밋하지 않는다. | 우진 |
| `docker-compose*.yml` | | | Pi 환경, 서비스 구성, 배포 | 명수 |

- Pi에서 직접 해야 하는 일(설치, 배포, 메모리·추론 시간 측정, ESP32 연결 테스트)은 명수가 한다.
- inference와 uploader는 PC의 Docker에서 개발한다. arm64에서 도는지는 PR마다 CI(arm64 러너)가 확인한다.
- `buffer/`는 uploader가 업로드 실패분을 쌓는 폴더로, 실행하면 생기고 커밋하지 않는다.

실행 방법은 저장소 루트 `README.md`의 "실행" 절.
