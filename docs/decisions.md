# 결정 기록

되돌리기 어려운 결정을 날짜순으로 적는다. 형식: 날짜, 결정, 이유, 버린 선택지.

## 2026-11-02 파트를 장비 단위 3개로 나눈다

- 결정: `esp32` `pi` `cloud` 3파트. 인원이 늘면 파트 안 하위 폴더를 한 명씩 맡는다.
- 이유: 폴더 = 장비 = 파트라서 담당 경계가 분명하고, 사람이 늘어도 구조와 브랜치 이름을 바꾸지 않는다.
- 버린 선택지: 컨테이너마다 파트 하나 (사람 수가 컨테이너 수에 묶인다).

## 2026-11-02 web을 파트로 분리하고 담당을 확정한다

- 결정: 파트를 `esp32`(대희) `pi`(명수·우진) `cloud`(도은) `web`(진아) 4개로 한다. pi 안에서는 Pi 환경·compose·gateway·CI를 명수, inference·모델 변환을 우진이 맡는다. `pi/uploader/`는 Supabase에 쓰는 코드라 cloud(도은)가 맡는다.
- 이유: 라즈베리 파이 실물을 명수가 가지고 있어서, Pi에서 해야 하는 일은 명수에게 모으고 나머지는 PC와 CI(arm64 러너)로 개발할 수 있게 나눴다. uploader를 테이블을 만든 사람이 맡으면 pi와 cloud의 경계가 "gateway가 uploader에 결과+사진을 넘긴다" 하나로 줄어든다.
- 버린 선택지: 우진이 Pi 환경·compose를 맡는 안 (Pi 없이 할 수 없다), web을 cloud 안에 두는 안 (담당이 달라 폴더를 나눴다).

## 2026-11-02 Pi 서비스를 gateway · inference · uploader 3개로 나눈다

- 결정: 수신·순서 관리(gateway), 판정(inference), 클라우드 저장(uploader)을 컨테이너로 분리한다.
- 이유: 메모리를 가장 많이 쓰는 inference에 따로 제한을 걸 수 있고, 클라우드가 느리거나 끊겨도 추론이 멈추지 않는다.
- 버린 선택지: gateway와 inference를 합친 2개 구성 (사진 전달이 한 번 줄지만 메모리 제한을 따로 걸 수 없다).

## 2026-11-02 CI는 바뀐 파트만, PR에서만 돈다

- 결정: `pull_request` 트리거만, 경로 필터로 바뀐 파트 job만 실행, 필수 검사는 `ci-ok` 하나.
- 이유: 지난 프로젝트에서 모든 PR이 전체를 검사하고 push·PR·병합마다 같은 코드를 2~3번 검사해 CI가 2분에서 8분으로 늘었다.
- 버린 선택지: 모든 PR에서 전체 검사.

## 2026-11-02 Pi gateway를 Tailscale Funnel로 인터넷에 연다

- 결정: Pi의 gateway(`/frame`)만 Tailscale Funnel의 HTTPS 주소로 인터넷에 연다. 프록시를 거친 요청은 `X-Device-Token`(팀 공용 토큰)을 검사하고, 같은 네트워크 요청은 지금처럼 토큰 없이 받는다.
- 이유: Pi는 현장 LAN에 한 대뿐이라 외부 네트워크에 있는 팀원의 ESP32가 실제 Pi 파이프라인에 사진을 보낼 길이 필요했다. Funnel은 도메인 없이 고정 HTTPS 주소를 주고, 공유기 포트포워딩이 필요 없으며, SSH 같은 다른 포트는 닫힌 채로 둔다.
- 버린 선택지: 공유기 포트포워딩 (SSH·포트가 인터넷에 노출된다), Cloudflare Tunnel (Cloudflare에 등록할 도메인이 필요하다. 도메인이 생기면 주소만 바꿔 옮길 수 있다), ngrok 무료 (월 1GB 전송 제한), 팀원 모두에게 SSH (Pi 전체 권한을 주게 된다).

## 2026-11-02 Pi 배포는 Pi의 self-hosted runner로, 팀원 누구나 Actions에서 누른다

- 결정: Pi에 GitHub Actions self-hosted runner(라벨 `pi`)를 서비스로 설치하고, `.github/workflows/deploy-pi.yml`(workflow_dispatch만)로 브랜치를 골라 `git checkout` → `docker compose up --build`를 한다. write 권한이 있는 팀원은 누구나 실행할 수 있다.
- 이유: Pi가 한 대뿐이라 배포·재빌드가 Pi 관리자(명수)에게 몰렸다. runner는 Pi에서 GitHub로 나가는 연결만 써서 새 포트를 열지 않고, 누가 언제 어느 커밋을 올렸는지 Actions 기록에 남는다. 배포 결과(커밋, 컨테이너 상태, 최근 로그)도 같은 화면에서 본다.
- 버린 선택지: 팀원에게 SSH (Pi 전체 권한, Funnel 결정 때 이미 뺐다), gateway에 배포용 엔드포인트 (인터넷에 열린 서비스가 Docker를 다루게 된다), dev 병합 때 자동 배포 (팀원이 Pi에서 시험 중인 브랜치를 덮어쓴다. 필요하면 나중에 push 트리거만 더한다), Watchtower 같은 이미지 자동 갱신 (이미지 레지스트리가 필요하다).
- 겹침 막기: 먼저 누른 deploy·release가 돌고 있으면 뒤의 실행은 기다리지 않고 바로 실패한다 (GitHub concurrency만 쓰면 기다리던 실행이 이유 없이 취소된다). deploy가 끝나면 Pi에 "시험 중" 표시(누가, 브랜치, 풀리는 시각)를 남겨 `hold_minutes` 동안 다른 사람의 deploy를 막는다. 막힌 이유는 실행 Summary에 남는다. 규칙은 `pi/deploy.sh` 하나에 두고, 명수가 Pi에서 직접 작업할 때도 같은 스크립트(`pi-deploy hold`·`release`)와 `~/.bashrc`의 docker 함수로 같은 표시를 따른다 (다른 사람이 시험 중이면 직접 `docker compose up` 등도 막힌다).
- 주의: public 저장소라 이 workflow에 pull_request·push 트리거를 넣지 않는다. 저장소 설정에서 외부 기여자 PR의 workflow 실행은 승인을 받게 둔다.
