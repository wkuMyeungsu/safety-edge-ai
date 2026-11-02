#!/usr/bin/env bash
# Pi 배포와 "시험 중" 표시. GitHub Actions(deploy-pi)와 Pi에서 직접 작업할 때 같은 규칙을 쓴다.
# Pi에는 deploy-pi가 실행될 때마다 ~/.local/bin/pi-deploy 로 최신본이 복사된다.
#
#   pi-deploy status                 지금 커밋, 시험 중인 사람, 컨테이너 상태, 최근 로그
#   pi-deploy deploy <ref> [분]      받아서 다시 빌드. 끝나면 [분](기본 30) 동안 시험 중 표시 (0 = 표시 안 함)
#   pi-deploy hold [분] [메모]       코드는 그대로 두고 시험 중 표시만 (측정, ESP32 시험 등. 기본 60분)
#   pi-deploy release                시험 중 표시 풀기
#   pi-deploy check                  다른 사람이 시험 중이면 실패 (~/.bashrc의 docker 함수가 부른다)
#
# 시험 중 표시: ~/.safety-edge-ai-deploy-lock 한 줄 "<누가> <무엇> <커밋> <풀리는 시각(epoch)>"
# 자기 표시에는 막히지 않는다. 시간이 지나면 저절로 풀린다.
set -euo pipefail

REPO="${PI_DIR:-$HOME/safety-edge-ai}"
LOCK="$HOME/.safety-edge-ai-deploy-lock"
ME="${GITHUB_ACTOR:-wkuMyeungsu}"   # Pi 셸에 들어오는 사람은 명수뿐이라 기본값을 명수 GitHub 아이디로 둔다
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/null}"

kst() { TZ=KST-9 date -d "@$1" +%H:%M; }   # Pi에 시간대 파일이 없어도 한국 시각
note() { echo "$1"; echo "### $1" >> "$SUMMARY"; }
fail() {
  if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::error::$1"; else echo "멈춤: $1" >&2; fi
  echo "### 멈춤: $1" >> "$SUMMARY"
  exit 1
}
minutes() { if ! [[ "$1" =~ ^[0-9]+$ ]] || [ "$1" -gt 240 ]; then fail "시간은 0~240분: $1"; fi; }

# 살아 있는 표시가 있으면 who what sha until 을 채우고 0, 없으면 1
held() {
  [ -f "$LOCK" ] || return 1
  read -r who what sha until < "$LOCK" || return 1
  [[ "$until" =~ ^[0-9]+$ ]] && [ "$(date +%s)" -lt "$until" ]
}

check() {
  if held && [ "$who" != "$ME" ]; then
    fail "$who 님이 $what ($sha)를 시험 중 ($(kst "$until")까지). $who 님에게 확인한 뒤 release하고 다시 한다"
  fi
}

hold() {  # hold <분> <무엇>
  if [ "$1" -eq 0 ]; then rm -f "$LOCK"; return; fi
  local until; until=$(( $(date +%s) + $1 * 60 ))
  echo "$ME $2 $(git -C "$REPO" rev-parse --short HEAD) $until" > "$LOCK"
  note "$ME 님 시험 중: $2, $(kst "$until")까지 다른 사람의 deploy·docker compose를 막음. 끝나면 release"
}

case "${1:-status}" in
  check)
    check ;;

  deploy)
    ref="${2:?올릴 브랜치 또는 커밋}"; min="${3:-30}"
    [[ "$ref" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]] || fail "ref 형식이 틀림: $ref"
    minutes "$min"
    check
    cd "$REPO"
    git fetch --prune origin
    # Pi에서 직접 고친 파일은 덮어쓰지 않는다 (.env·buffer·models는 git 밖이라 상관없다)
    if ! git diff --quiet || ! git diff --cached --quiet; then
      git status -s; fail "Pi 저장소($REPO)에 커밋 안 된 변경이 있음. 명수에게 알린다"
    fi
    if ! git checkout -q --detach "origin/$ref" 2>/dev/null && ! git checkout -q --detach "$ref" 2>/dev/null; then
      fail "브랜치·커밋을 찾지 못함: $ref (push했는지 확인)"
    fi
    git log -1 --format='배포할 커밋 %h %s (%an)'
    (cd pi && COMMIT=$(git rev-parse --short HEAD) docker compose up --build -d --wait --wait-timeout 180 && docker image prune -f)
    hold "$min" "$ref" ;;

  hold)
    min="${2:-60}"; what="${3:-직접작업}"
    minutes "$min"
    if [ -z "$what" ] || [[ "$what" == *[[:space:]]* ]]; then fail "메모는 띄어쓰기 없이: $what"; fi
    check
    hold "$min" "$what" ;;

  release)
    if [ -f "$LOCK" ]; then
      read -r who what sha _ < "$LOCK" || true
      rm -f "$LOCK"
      note "$ME 님이 ${who:-?} 님의 시험 중 표시(${what:-?} ${sha:-?})를 풀었음"
    else
      note "풀 시험 중 표시가 없음"
    fi ;;

  status)
    cd "$REPO"
    git log -1 --format='지금 Pi 커밋 %h %s (%an, %cd)' --date=iso
    if held; then echo "시험 중: $who 님, $what ($sha), $(kst "$until")까지"; else echo "시험 중 표시 없음 (누구나 deploy 가능)"; fi
    cd pi
    docker compose ps
    curl -fsS http://localhost:8001/health; echo
    docker compose logs --no-color --tail 80 ;;

  *)
    sed -n '2,13p' "$0"; exit 2 ;;
esac
