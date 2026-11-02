# pi

라즈베리 파이 5에서 Docker로 실행하는 3개 서비스.

| 폴더 | 서비스 | 포트 | 하는 일 |
|---|---|---|---|
| `gateway/` | gateway | 8001 (외부 공개) | esp32 사진 수신, 대기 줄, inference → uploader 호출 순서 |
| `inference/` | inference | 8003 (내부) | PPE 모델로 안전모·조끼 판별 |
| `uploader/` | uploader | 8004 (내부) | Supabase 기록·사진 저장, 실패 시 재시도 |
| `models/` | (볼륨) | | 모델 파일 위치. `*.onnx`는 커밋하지 않는다. |

`buffer/`는 uploader가 업로드 실패분을 쌓는 폴더로, 실행하면 생기고 커밋하지 않는다.

실행 방법은 저장소 루트 `README.md`의 "실행" 절.
