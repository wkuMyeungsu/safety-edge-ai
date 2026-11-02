# Edge AI 스마트 산업 안전 시스템

ESP32-S3가 사람을 감지한 프레임만 라즈베리 파이 5로 보내고, 파이가 안전모·조끼 착용 여부를 판별해 위반 건을 Supabase에 기록한다. 웹은 Supabase를 조회해 위반 기록을 보여 준다.

```
[esp32]  ──JPEG──▶  [pi]  ──기록·사진──▶  [cloud]
사람 감지            안전모·조끼 판별         Supabase + Web
```

전체 구조는 `docs/architecture.html`, 파트 사이 데이터 형식은 `docs/contracts/`.

## 파트 · 담당

파트는 장비 단위로 3개이고, 최상위 폴더 이름이 파트 이름이다.

| 파트 | 폴더 | 하는 일 | 담당 |
|---|---|---|---|
| `esp32` | `esp32/` | Edge Impulse 사람 감지, 카메라 펌웨어, 파이로 사진 전송 | 미정 |
| `pi` | `pi/` | PPE 모델 ONNX 변환·추론, gateway·inference·uploader 컨테이너 | 미정 |
| `cloud` | `cloud/` | Supabase 테이블·버킷·RLS, 웹 페이지 | 미정 |

## 인원이 늘 때

파트 폴더 안의 하위 폴더가 한 사람이 맡을 수 있는 단위다. 사람이 추가되면 하위 폴더 하나를 맡고 아래 표의 담당 칸만 바꾼다. 폴더 구조와 브랜치의 파트 이름은 바뀌지 않는다.

| 파트 | 하위 폴더 | 하는 일 | 담당 |
|---|---|---|---|
| `esp32` | `esp32/model/` | Edge Impulse 프로젝트, 감지율 확인 | 파트 담당 |
| `esp32` | `esp32/firmware/` | 카메라 설정, 쿨다운, HTTP POST | 파트 담당 |
| `pi` | `pi/inference/` + `pi/models/` | ONNX 변환·검증, 추론 서버 | 파트 담당 |
| `pi` | `pi/gateway/` + `pi/docker-compose.yml` | 사진 수신, 대기 줄, 호출 순서, Pi 환경 | 파트 담당 |
| `pi` | `pi/uploader/` | Supabase 저장, 실패 시 재시도 | 파트 담당 |
| `cloud` | `cloud/supabase/` | 테이블, 버킷, RLS | 파트 담당 |
| `cloud` | `cloud/web/` | 위반 기록 웹 페이지 | 파트 담당 |

## 실행 (라즈베리 파이)

필요한 것: Raspberry Pi OS 64-bit, Docker, Docker Compose 2.24 이상.

```bash
cd pi
cp ../.env.example .env        # Supabase 값 채우기
docker compose up --build -d   # 전체
docker compose ps              # 상태 (healthy 확인)
docker stats                   # 메모리 사용량
docker compose down            # 종료
```

- 지금 `pi/*`의 서버는 `/health`만 답하는 뼈대다. 담당자가 자기 폴더의 `main.py`·`Dockerfile`·`requirements.txt`를 채운다.
- 외부에 열리는 포트는 gateway의 `8001`뿐이다. 컨테이너끼리는 서비스 이름으로 부른다 (`http://inference:8003`).

## 브랜치

- `main`: 최종본. `dev`: 통합. 둘 다 직접 push하지 않고 PR로만 합친다.
- 작업 브랜치: `<태그>/<파트>/<기능>`. 태그는 `feature` `fix` `docs` `refactor` `chore`, 파트는 `esp32` `pi` `cloud`.
  예: `feature/esp32/person-detect`, `feature/pi/onnx-inference`, `feature/cloud/web-list`
- 여러 파트 폴더를 함께 바꾸면 파트 자리에 `common`을 쓴다. 예: `docs/common/contracts`
- 작업 브랜치는 `dev`에서 만들고 `dev`로 PR을 올린다. 병합 후 삭제한다.
- 커밋 메시지: `<타입>(<파트>): <요약>`. 예: `feat(pi): gateway 대기 줄 추가`
- `.env`, `config.h`, 모델 가중치(`*.onnx` `*.pt`), 영상은 커밋하지 않는다.
