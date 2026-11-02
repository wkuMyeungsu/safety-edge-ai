# Edge AI 스마트 산업 안전 시스템

ESP32-S3가 사람을 감지한 프레임만 라즈베리 파이 5로 보내고, 파이가 안전모·조끼 착용 여부를 판별해 위반 건을 Supabase에 기록한다. 웹은 Supabase를 조회해 위반 기록을 보여 준다.

```
[esp32]  ──JPEG──▶  [pi]  ──기록·사진──▶  [cloud]  ◀──조회──  [web]
사람 감지            안전모·조끼 판별         Supabase              위반 기록 화면
```

전체 구조는 `docs/architecture.html`, 파트 사이 데이터 형식은 `docs/contracts/`.
담당·원격 시험(Tailscale Funnel)·배포(deploy-pi)·브랜치·CI 방법은 `docs/cooperation.html`.
Pi gateway API는 `docs/api-manual.html`.

## 파트 · 담당

최상위 폴더 이름이 파트 이름이다. 라즈베리 파이 실물은 명수가 가지고 있다.

| 파트 | 하는 일 | 담당 |
|---|---|---|
| `esp32` | Edge Impulse 사람 감지, 카메라 펌웨어, 파이로 사진 전송 | 대희 (@widee2018-code) |
| `pi` | Pi 환경·배포·측정, gateway, PPE 모델 ONNX 변환·추론 | 명수 (@wkuMyeungsu), 우진 (@MOTNV) |
| `cloud` | Supabase 테이블·버킷·RLS, Supabase에 기록을 쓰는 uploader | 도은 (@ki543219) |
| `web` | 위반 기록 웹 페이지 | 진아 (@Binary-Ah) |

## 폴더별 담당

실제로 고치는 범위는 이 표가 기준이다. 담당이 바뀌거나 사람이 늘면 이 표와 `.github/CODEOWNERS`만 고친다. 폴더 구조와 브랜치의 파트 이름은 바꾸지 않는다.

| 폴더 | 하는 일 | 담당 |
|---|---|---|
| `esp32/` | Edge Impulse 모델, 카메라 설정, 쿨다운, HTTP POST | 대희 |
| `pi/docker-compose*.yml` | Pi 환경(OS·Docker), 서비스 구성, 배포, 메모리 측정 | 명수 |
| `pi/gateway/` | 사진 수신, 대기 줄, inference → uploader 호출 순서 | 명수 |
| `.github/` | CI | 명수 |
| `pi/inference/` + `pi/models/` | ONNX 변환·검증, 추론 서버 | 우진 |
| `pi/uploader/` | Supabase 저장, 실패 시 버퍼·재시도 | 도은 |
| `cloud/supabase/` | 테이블, 버킷, RLS | 도은 |
| `web/` | 위반 기록 웹 페이지 | 진아 |
| `docs/contracts/` | 파트 사이 데이터 형식 | 경계 양쪽 담당 |

`tests/`는 같은 폴더 이름 아래에 같은 담당이다 (예: `tests/pi/inference/`는 우진).

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

- 모델 파일(`pi/models/ppe_yolov8.onnx`)은 git에 없다. 없으면 inference가 `/health`에 `model_loaded: false`로 뜨고 판정은 `503`이다. 받는 법은 `pi/models/README.md`.
- 외부에 열리는 포트는 gateway의 `8001`뿐이다. 컨테이너끼리는 서비스 이름으로 부른다 (`http://inference:8003`).
- 실제 Pi에 올리기는 Actions → `deploy-pi` → Run workflow (팀원 누구나, `pi/README.md` "Pi 배포").

## 테스트 · CI

- 테스트는 `tests/<파트>/`에 `test_*.py`로 추가한다. 규칙은 `tests/README.md`.
- PR을 올리면 GitHub Actions(`.github/workflows/ci.yml`)가 **바뀐 파트만** 검사한다.
  - `pi/` → arm64 러너에서 컨테이너 빌드·기동 후 `tests/pi`
  - `esp32/` → 펌웨어 컴파일 후 `tests/esp32`
  - `cloud/` → 로컬 Supabase에 `schema.sql` 적용 후 `tests/cloud`
  - `web/` → `tests/web`
  - `pi/uploader/`는 Pi 컨테이너라서 `pi` job에서 검사한다
  - `docs/contracts/`·`tests/contracts/`가 바뀌거나 dev → main PR이면 전부
- 마지막 `ci-ok`가 초록불이어야 dev·main에 병합된다.

## 브랜치

- `main`: 최종본. `dev`: 통합. 둘 다 직접 push하지 않고 PR로만 합친다.
- 작업 브랜치: `<태그>/<파트>/<기능>`. 태그는 `feature` `fix` `docs` `refactor` `chore`, 파트는 `esp32` `pi` `cloud` `web`.
  예: `feature/esp32/person-detect`, `feature/pi/onnx-inference`, `feature/cloud/schema`, `feature/web/log-list`
- 파트 이름은 고치는 폴더의 최상위 이름을 쓴다. `pi/uploader/`를 고치면 담당이 cloud여도 `feature/pi/<기능>`.
- 여러 파트 폴더를 함께 바꾸면 파트 자리에 `common`을 쓴다. 예: `docs/common/contracts`
- 작업 브랜치는 `dev`에서 만들고 `dev`로 PR을 올린다. 병합 후 삭제한다.
  - GitHub의 브랜치는 PR이 병합되면 자동으로 지워진다 (저장소 설정).
  - 내 PC의 브랜치는 직접 지운다:

    ```bash
    git switch dev && git pull --prune   # 최신 dev 받기, 지워진 원격 브랜치 정보 정리
    git branch -d <병합된 브랜치>          # 병합되지 않았으면 지워지지 않는다 (안전)
    ```
- 커밋 메시지: `<타입>(<파트>): <요약>`. 예: `feat(pi): gateway 대기 줄 추가`
- `.env`, `config.h`, 모델 가중치(`*.onnx` `*.pt`), 영상은 커밋하지 않는다.
