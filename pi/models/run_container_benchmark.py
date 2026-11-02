"""ARM64 추론 컨테이너의 실제 HTTP 판정·시간·cgroup 메모리를 측정한다."""

import argparse
import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from run_http_smoke import ROOT, git, request_json, run


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, timeout=180).strip()


def memory(container):
    result = {}
    for name in ("memory.current", "memory.peak", "memory.max", "memory.swap.max", "memory.events", "cpu.max"):
        value = docker("exec", container, "cat", f"/sys/fs/cgroup/{name}")
        if name == "memory.events":
            result[name] = {key: int(number) for key, number in (line.split() for line in value.splitlines())}
        else:
            result[name] = int(value) if value.isdigit() else value
    status = docker("exec", container, "cat", "/proc/1/status")
    result["process_status"] = {
        line.split(":", 1)[0]: line.split(":", 1)[1].strip()
        for line in status.splitlines() if line.startswith(("Name:", "VmRSS:", "VmHWM:", "Threads:"))
    }
    return result


def benchmark(args):
    commit = git("rev-parse", "HEAD")
    if git("status", "--porcelain", "--", "pi/inference", "pi/models/run_container_benchmark.py", "pi/models/run_http_smoke.py"):
        raise ValueError("추론 코드와 측정 도구를 먼저 커밋하세요")
    info = json.loads(docker("image", "inspect", args.image))[0]
    if (info["Os"], info["Architecture"]) != ("linux", "arm64"):
        raise ValueError("linux/arm64 이미지가 필요함")
    if (info["Config"].get("Labels") or {}).get("org.opencontainers.image.revision") != commit:
        raise ValueError("현재 커밋 revision label로 이미지를 다시 빌드하세요")
    container = "safety-edge-bench-" + uuid.uuid4().hex[:12]
    created = False
    try:
        docker("create", "--name", container, "--platform", "linux/arm64",
               "--cpus", "3", "--memory", "1g", "--memory-swap", "1g",
               "--publish", "127.0.0.1::8003", "--env", "ORT_THREADS=3",
               "--env", "MODEL_PATH=/models/ppe_yolov8.onnx",
               "--mount", f"type=bind,source={args.model.resolve()},target=/models/ppe_yolov8.onnx,readonly",
               info["Id"])
        created = True
        docker("start", container)
        details = json.loads(docker("inspect", container))[0]
        port = details["NetworkSettings"]["Ports"]["8003/tcp"][0]
        if port["HostIp"] != "127.0.0.1":
            raise ValueError("벤치마크 포트는 loopback에만 열려야 함")
        url = f"http://127.0.0.1:{port['HostPort']}"
        deadline = time.monotonic() + 180
        while True:
            try:
                health, _ = request_json(url + "/health", timeout=2)
            except (OSError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("컨테이너 시작 시간 초과") from None
                time.sleep(1)
                continue
            if not health.get("model_loaded"):
                raise ValueError(f"모델 로드 실패: {health}")
            break

        # 실제 마운트 파일과 실행 이미지의 코드를 확인한다. 무거운 런타임 import는 하지 않는다.
        identity_code = """
import hashlib, importlib.metadata, json, platform, sys
from pathlib import Path
def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
print(json.dumps({
    'machine': platform.machine(), 'python': sys.version,
    'model_sha256': sha(Path('/models/ppe_yolov8.onnx')),
    'code_sha256': {p.name: sha(p) for p in Path('/app').glob('*.py')},
    'requirements_sha256': sha(Path('/app/requirements.txt')),
    'packages': {p: importlib.metadata.version(p) for p in
                 ['onnxruntime', 'numpy', 'opencv-python-headless', 'fastapi', 'uvicorn']}
}))
"""
        identity = json.loads(docker("exec", container, "python", "-c", identity_code))
        local_files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (ROOT / "pi/inference").glob("*.py")}
        if identity["code_sha256"] != local_files:
            raise ValueError("컨테이너 코드가 현재 저장소와 다름")
        requirements_sha = hashlib.sha256((ROOT / "pi/inference/requirements.txt").read_bytes()).hexdigest()
        if identity["requirements_sha256"] != requirements_sha:
            raise ValueError("컨테이너 requirements가 현재 저장소와 다름")
        with args.model.open("rb") as stream:
            if identity["model_sha256"] != hashlib.file_digest(stream, "sha256").hexdigest():
                raise ValueError("컨테이너 모델 해시 불일치")
        before = memory(container)
        if before["memory.max"] != 1073741824 or before["memory.swap.max"] != 0:
            raise ValueError("1 GiB 메모리·swap 비활성 제한이 적용되지 않음")
        print(f"모델 준비 완료: {url}; ARM64 HTTP 측정 시작", flush=True)
        report = run(SimpleNamespace(url=url, model=args.model, manifest=args.manifest,
                                    server_label=args.server_label, repeats=args.repeats, parallel=args.parallel))
        after = memory(container)
        state = json.loads(docker("inspect", container))[0]["State"]
        if after["memory.events"].get("oom", 0) or after["memory.events"].get("oom_kill", 0) or state["OOMKilled"]:
            raise ValueError("측정 중 OOM 발생")
        report["virtual_environment"] = {
            "is_raspberry_pi_hardware": False,
            "interpretation": "ARM64 컨테이너 실행 검증. QEMU/호스트 CPU의 시간·메모리이므로 Pi 5 성능으로 환산할 수 없음.",
            "image_id": info["Id"], "image_revision": commit,
            "platform": "linux/arm64", "container_identity": identity,
            "docker_server": json.loads(docker("version", "--format", "{{json .Server}}")),
            "limits": {"memory_bytes": details["HostConfig"]["Memory"],
                       "memory_swap_bytes": details["HostConfig"]["MemorySwap"],
                       "nano_cpus": details["HostConfig"]["NanoCpus"], "ort_threads": 3},
            "memory_before": before, "memory_after": after,
            "memory_note": "cgroup v2 바이트 단위. memory.peak는 컨테이너 시작부터 모델 로드·해시 확인·추론·계측 보조 프로세스를 포함한 최대값. QEMU 실행 시 그 비용도 포함. memory.current는 순간값이며 Docker working set이나 모델 파일 크기와 다름. process_status는 PID 1의 /proc 값으로 QEMU 환경에서 네이티브 Pi RSS로 해석하지 않음.",
        }
        return report
    except Exception:
        if created:
            print(docker("logs", "--tail", "30", container), flush=True)
        raise
    finally:
        if created:
            docker("rm", "--force", container)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--server-label", required=True, help="실제 호스트 CPU·OS·QEMU 버전 등")
    parser.add_argument("--model", type=Path, default=ROOT / "pi/models/ppe_yolov8.onnx")
    parser.add_argument("--manifest", type=Path, default=ROOT / "pi/models/model-v1.json")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--parallel", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100 or not 2 <= args.parallel <= 64:
        parser.error("repeats는 1~100, parallel은 2~64여야 함")
    if args.output.exists():
        parser.error("기존 보고서를 덮어쓰지 않음")
    try:
        report = benchmark(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except Exception as exc:
        parser.exit(1, f"컨테이너 측정 실패: {exc}\n")
    print(json.dumps({"output": str(args.output), "inference": report["inference"],
                      "http": report["http"], "memory": report["virtual_environment"]["memory_after"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
