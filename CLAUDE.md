# CLAUDE.md

이 저장소에서 사람과 Claude Code가 함께 따르는 규칙이다. 작업을 시작하기 전에 끝까지 읽는다.

## 0. 먼저 읽을 문서

1. `README.md`: 파트·담당, 실행 방법, 브랜치 규칙
2. `docs/architecture.html`: 장비·컨테이너 구조와 처리 순서
3. `docs/contracts/`: 파트 사이에 주고받는 데이터 형식
4. 작업할 파트의 `README.md` (`esp32/`, `pi/`, `cloud/`)와 `tests/README.md`

## 1. 담당 영역

- 파트는 `esp32` `pi` `cloud` 3개이고, 최상위 폴더 이름이 곧 파트 이름이다. 담당자는 `README.md` 표에 있다.
- 내 파트 폴더와 `tests/<내 파트>/`만 고친다. 다른 파트 폴더는 읽기만 한다.
- 다른 파트를 고쳐야 문제가 풀리면 고치지 말고 멈춘 뒤, 무엇을 왜 바꿔야 하는지 담당자에게 알린다.
- 공용 파일(`README.md`, `CLAUDE.md`, `docs/`, `.github/`, `pytest.ini`, `tests/conftest.py`, `.env.example`)은 관련 담당자와 상의한 뒤 바꾼다.
- 인원이 늘면 파트 안 하위 폴더 단위로 나눠 맡는다. 폴더 구조와 파트 이름은 바꾸지 않는다.

## 2. 개발 환경

| 대상 | 기준 |
|---|---|
| ESP32 | Seeed XIAO ESP32S3, FQBN `esp32:esp32:XIAO_ESP32S3:PSRAM=opi`, esp32 코어 3.3.12 (`.github/workflows/ci.yml`과 같은 값) |
| 라즈베리 파이 | Pi 5 4GB, Raspberry Pi OS 64-bit, Docker Compose 2.24 이상 |
| 컨테이너 | `python:3.12-slim`, 패키지는 서비스 폴더의 `requirements.txt`에 버전을 고정해 적는다 |

- 위 값을 바꾸면 ci.yml과 이 표를 같은 PR에서 함께 고치고, PR 설명에 "환경 갱신 필요"를 적는다.
- Pi 메모리는 4GB다. 모델은 서버 시작 때 한 번만 불러오고, uvicorn worker는 1개로 둔다.
- Pi 이미지에는 torch·ultralytics를 넣지 않는다. 모델 변환은 PC에서 하고 ONNX만 쓴다.

## 3. 커밋하지 않는 것

- `.env`, `esp32/firmware/safety_cam/config.h` (Wi-Fi 비밀번호, Supabase key, IP처럼 사람마다 다른 값)
- 모델 가중치 `*.onnx` `*.pt`. ONNX는 GitHub Release `model-v1`에 올리고 `pi/models/README.md`에 SHA256을 적는다.
- 영상 `*.mp4` `*.mov`, `pi/buffer/`
- Supabase service key는 pi의 `.env`에만 둔다. 웹(`cloud/web/`)에는 anon key만 쓴다.

예외: Edge Impulse Arduino 라이브러리 zip은 `esp32/model/`에 커밋한다 (CI 컴파일용).

## 4. 파트 사이 계약

- 형식은 구현 전에 `docs/contracts/`에 적고, 보내는 쪽과 받는 쪽 담당자가 둘 다 확인한다.
- 계약을 바꾸는 커밋은 메시지에 `[contract]`를 붙인다. 이 경로가 바뀌면 CI가 모든 파트를 검사한다.
- 다른 파트가 아직 없으면 가짜로 대신한다. 예: ESP32 대신 `curl`로 사진 POST, Supabase 대신 uploader 버퍼.
- 계약이 바뀐 배포는 받는 쪽부터 올린다: Supabase 스키마 → pi → web → esp32.

## 5. 테스트와 CI

- 테스트는 `tests/<파트>/`에 `test_*.py`로 추가한다. 서비스 코드를 import하지 말고 HTTP로 부른다.
- 테스트는 문자열이 아니라 응답 코드·JSON 필드·출처로 판정한다.
- 마커: 모델이 필요하면 `model`, Supabase가 필요하면 `supabase`, Pi에서만 의미 있는 측정은 `pi`.
- PR은 `ci-ok`가 초록불이어야 병합된다. 실패하면 테스트를 지우거나 건너뛰게 하지 말고 원인을 고친다.
- CI가 느려지는 변경(무거운 빌드·다운로드 추가)은 캐시를 같은 PR에 넣는다.
- 병합은 앞 PR의 CI가 끝난 뒤 하나씩 한다.

## 6. 지금 도는 것이 최신인지

- `git pull` 뒤에는 `docker compose up --build`로 다시 빌드한다. `--build`가 없으면 예전 이미지가 돈다.
- 펌웨어는 시리얼 첫 줄에 `FW_VERSION`을 출력하고, 바꿀 때마다 올린다.
- 측정한 숫자(추론 시간, 메모리, 감지율)는 어느 커밋에서 쟀는지 함께 적는다.

## 7. 큰 결정

- 모델 교체, 컨테이너 추가·삭제, 계약 변경처럼 되돌리기 어려운 결정은 선택지를 2개 이상 비교한 뒤 정한다.
- 정한 내용은 `docs/decisions.md`에 날짜, 결정, 이유, 버린 선택지를 한 항목으로 남긴다.

## 8. 브랜치와 커밋

- `main`(최종본)과 `dev`(통합)에는 직접 push하지 않는다. PR로만 합치고, 병합 방식은 Create a merge commit만 쓴다.
- 작업 브랜치: `<태그>/<파트>/<기능>`. 태그는 `feature` `fix` `docs` `refactor` `chore`, 파트는 `esp32` `pi` `cloud` `common`.
- 작업 브랜치는 `dev`에서 만들고 `dev`로 PR을 올린다. 병합 후 삭제한다.
- 커밋 메시지: `<타입>(<파트>): <요약>`. 타입은 `feat` `fix` `docs` `refactor` `chore`. 예: `feat(pi): gateway 대기 줄 추가`
- 실수로 로컬 `dev`에 커밋했다면 `git switch -c <작업 브랜치>` 뒤 `git branch -f dev origin/dev`로 옮긴다.
