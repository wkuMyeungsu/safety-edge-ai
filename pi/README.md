# pi

라즈베리 파이 5에서 Docker로 실행하는 3개 서비스. Pi 실물은 명수가 가지고 있다.

| 폴더 | 서비스 | 포트 | 하는 일 | 담당 |
|---|---|---|---|---|
| `gateway/` | gateway | 8001 (외부 공개) | esp32 사진 수신, 대기 줄, inference → uploader 호출 순서 | 명수 |
| `inference/` | inference | 8003 (내부) | PPE 모델로 안전모·조끼 판별 | 우진 |
| `uploader/` | uploader | 8004 (내부) | Supabase 기록·사진 저장, 실패 시 재시도 | 도은 (cloud) |
| `models/` | (볼륨) | | 모델 파일 위치. `*.onnx`는 커밋하지 않는다. | 우진 |
| `docker-compose*.yml` | | | Pi 환경, 서비스 구성, 배포 | 명수 |

- 배포·재빌드는 팀원 누구나 GitHub Actions의 `deploy-pi`로 한다 (아래 "Pi 배포").
- 그 밖에 Pi에서 직접 해야 하는 일(설치, 모델 파일 교체, 메모리 측정)은 명수가 한다.
- inference와 uploader는 PC의 Docker에서 개발한다. arm64에서 도는지는 PR마다 CI(arm64 러너)가 확인한다.
- `buffer/`는 uploader가 업로드 실패분을 쌓는 폴더로, 실행하면 생기고 커밋하지 않는다.

실행 방법은 저장소 루트 `README.md`의 "실행" 절.

## Pi 배포

### 쓰는 법 (팀원 누구나)

1. GitHub 저장소 → Actions → `deploy-pi` → Run workflow
2. `ref`에 올릴 브랜치(기본 `dev`), `action`을 고른다.
   - `deploy`: 받아서 다시 빌드. 끝나면 `hold_minutes`(기본 30분) 동안 "시험 중"으로 표시되어 다른 사람의 `deploy`가 막힌다
   - `status`: 바꾸지 않고 보기만 (언제든 된다)
   - `release`: 시험 중 표시를 푼다. **시험이 끝나면 올린 사람이 누른다**
3. 끝나면 마지막 단계 "상태·최근 로그"에서 지금 Pi 커밋, 시험 중인 사람, `docker compose ps`, `/health`, 최근 로그 80줄을 본다.

- 막히면 기다리지 않고 바로 실패한다. 이유는 실행 화면 맨 위 Summary와 실행 목록의 빨간 표시에 남는다.
  - `다른 배포가 아직 돌고 있어 멈춤: deploy feature/pi/x (MOTNV), 14:35 시작 · <링크>`: 끝난 뒤 다시 누른다
  - `MOTNV 님이 feature/pi/x (abc1234)를 시험 중이라 멈춤 (15:05까지)`: 그 사람에게 확인한 뒤 `release`를 누르고 다시 `deploy`
- 같은 사람은 자기 시험 중 표시에 막히지 않는다 (고쳐서 다시 올리기). 시간이 지나면 표시는 저절로 풀린다.
- 실행 목록에 `deploy feature/pi/x (MOTNV)`처럼 누가 무엇을 올렸는지 보인다.
- 시험이 끝나면 `dev`로 다시 올려 둔다 (`hold_minutes` 0이면 표시를 남기지 않는다).

### Pi에서 직접 작업할 때 (명수)

Actions와 같은 규칙을 `pi-deploy`(= `pi/deploy.sh`, deploy-pi가 돌 때마다 최신본으로 바뀜)로 쓴다.

```bash
pi-deploy status                     # 지금 커밋, 시험 중인 사람, 컨테이너 상태
pi-deploy hold 60 메모리측정          # 측정·ESP32 시험 동안 다른 사람의 deploy를 막는다 (메모는 띄어쓰기 없이)
pi-deploy deploy feature/pi/xxx 30   # Actions의 deploy와 같다
pi-deploy release                    # 끝나면 푼다
```

- 다른 사람이 시험 중이면 `docker compose up·down·restart·stop·build` 같은 바꾸는 명령도 막힌다 (`~/.bashrc`의 docker 함수, 아래 설치). `ps`·`logs`·`exec`는 된다.
- 급할 때는 `command docker compose ...`로 우회한다. 우회했으면 팀 채널에 알린다.
- 실패하면 컨테이너는 직전 이미지로 돌지 않을 수 있다. 로그를 보고 고친 뒤 다시 올리거나 `dev`를 올린다.
- 모델 파일(`models/*.onnx`)과 `.env`는 git 밖이라 배포가 바꾸지 않는다. 바꿀 일이 있으면 명수에게 요청한다.
- 로그는 public 저장소라 누구나 볼 수 있다. 비밀값을 로그에 찍지 않는다.

### Pi에 runner 설치 (명수, 한 번만)

```bash
# 1) 배포에 쓰는 저장소 (이미 다른 곳에 있으면 저장소 변수 PI_DIR에 그 경로를 적는다)
git clone https://github.com/wkuMyeungsu/safety-edge-ai ~/safety-edge-ai
cp ~/safety-edge-ai/.env.example ~/safety-edge-ai/pi/.env   # 값 채우기

# 2) runner: GitHub → Settings → Actions → Runners → New self-hosted runner → Linux · ARM64
#    화면의 download 명령을 그대로 실행한 뒤, config만 라벨을 붙여 실행한다
./config.sh --url https://github.com/wkuMyeungsu/safety-edge-ai --token <화면의 토큰> --name rpi5 --labels pi --unattended
sudo usermod -aG docker "$USER"         # runner가 docker를 쓸 수 있게
sudo ./svc.sh install "$USER" && sudo ./svc.sh start   # 재부팅해도 자동 시작

# 3) 직접 작업도 시험 중 표시를 따르게: pi-deploy를 PATH에 두고 docker 함수를 ~/.bashrc에 넣는다
install -D -m 755 ~/safety-edge-ai/pi/deploy.sh ~/.local/bin/pi-deploy   # 이후로는 deploy-pi가 갱신한다
cat >> ~/.bashrc <<'BASHRC'
# safety-edge-ai: 다른 사람이 시험 중이면 docker compose의 바꾸는 명령을 막는다 (ps·logs·exec는 된다)
# 급할 때 우회: command docker compose ...
docker() {
  if [ "${1:-}" = compose ]; then
    for a in "$@"; do
      case "$a" in up|down|restart|stop|start|build|rm|kill|pull|create|run)
        ~/.local/bin/pi-deploy check || return 1; break ;;
      esac
    done
  fi
  command docker "$@"
}
BASHRC
```

- GitHub → Settings → Actions → General → "Fork pull request workflows from outside collaborators"를 "Require approval for all outside collaborators"로 둔다 (public 저장소에서 남의 PR이 Pi runner를 쓰지 못하게).
- runner 상태는 Settings → Actions → Runners에서 `rpi5`가 Idle인지 본다.
