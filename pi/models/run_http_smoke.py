"""실행 중인 실제 모델을 HTTP로 반복 검사하고 판정·응답 시간 보고서를 저장한다."""

import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

ROOT = Path(__file__).resolve().parents[2]


def request_json(url, photo=None, timeout=60):
    request = urllib.request.Request(url, data=photo)
    if photo is not None:
        request.add_header("Content-Type", "image/jpeg")
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    return body, round((time.perf_counter() - started) * 1000, 3)


def timings(values):
    ordered = sorted(values)
    return {"count": len(values), "median_ms": round(statistics.median(values), 3),
            "p95_ms": ordered[math.ceil(len(values) * 0.95) - 1], "max_ms": max(values)}


def git(*arguments):
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments], text=True).strip()


def run(args):
    base = args.url.rstrip("/")
    health, _ = request_json(base + "/health", timeout=5)
    if health.get("model_loaded") is not True:
        raise ValueError(f"실제 모델이 불러와지지 않음: {health}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    with args.model.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != manifest["sha256"]:
        raise ValueError("로컬 ONNX와 manifest SHA256이 다름")
    if health["model"] != manifest["file"] or health["classes"] != manifest["classes"]:
        raise ValueError("서버의 모델 이름·클래스가 manifest와 다름")
    if git("status", "--porcelain", "--", "pi/inference"):
        raise ValueError("추론 코드 변경을 먼저 커밋하고 서버를 다시 시작하세요")

    expected = json.loads((ROOT / "tests/pi/inference/expected.json").read_text(encoding="utf-8"))
    photos, cases, all_http, all_infer = {}, [], [], []
    for name, want in expected.items():
        if name.startswith("_"):
            continue
        path = ROOT / "tests/pi/inference/images" / name
        if not path.is_file():
            path = ROOT / "tests/fixtures/images" / name
        photos[name] = path.read_bytes()
        case = {"image": name, "expected": want, "samples": []}
        for iteration in range(args.repeats + 1):
            body, elapsed = request_json(base + "/predict", photos[name])
            for field, value in want.items():
                if body[field] != value:
                    raise ValueError(f"{name}: {field}={body[field]!r}, 기대 {value!r}")
            if iteration == 0:  # 사진마다 한 번 예열, 측정에서 제외
                case["prediction"] = body
                continue
            case["samples"].append({"http_ms": elapsed, "infer_ms": body["infer_ms"]})
            all_http.append(elapsed)
            all_infer.append(body["infer_ms"])
        case["http"] = timings([sample["http_ms"] for sample in case["samples"]])
        case["inference"] = timings([sample["infer_ms"] for sample in case["samples"]])
        cases.append(case)

    ready = Barrier(args.parallel + 1)
    first_name = next(iter(photos))

    def parallel_predict():
        ready.wait(timeout=15)
        return request_json(base + "/predict", photos[first_name])

    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        pending = [pool.submit(parallel_predict) for _ in range(args.parallel)]
        ready.wait(timeout=15)
        time.sleep(0.3)
        unfinished = sum(not task.done() for task in pending)
        live_health, health_ms = request_json(base + "/health", timeout=1)
        if live_health.get("model_loaded") is not True:
            raise ValueError("동시 요청 중 모델 상태가 바뀜")
        for task in pending:
            body, _ = task.result()
            for field, value in expected[first_name].items():
                if body[field] != value:
                    raise ValueError(f"동시 요청의 판정 불일치: {body}")
    return {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_commit": git("rev-parse", "HEAD"),
        "server_label": args.server_label,
        "client_platform": platform.platform(),
        "model_sha256_local": digest,
        "model_identity_note": "서버 /health의 이름·클래스와 로컬 파일 해시를 확인함. 서버 파일의 해시는 HTTP로 제공되지 않으므로 MODEL_PATH를 별도로 확인해야 함.",
        "health": health,
        "warmup_per_image": 1,
        "repeats_per_image": args.repeats,
        "http": timings(all_http),
        "inference": timings(all_infer),
        "concurrency": {"requests": args.parallel, "pending_at_health": unfinished,
                        "health_ms": health_ms, "all_predictions_match": True},
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8003")
    parser.add_argument("--model", type=Path, default=ROOT / "pi/models/ppe_yolov8.onnx")
    parser.add_argument("--manifest", type=Path, default=ROOT / "pi/models/model-v1.json")
    parser.add_argument("--server-label", required=True, help="서버의 실제 장비·OS (PC 결과를 Pi로 표시하지 않기)")
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--parallel", type=int, default=48)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100 or not 2 <= args.parallel <= 64:
        parser.error("repeats는 1~100, parallel은 2~64여야 함")
    if args.output.exists():
        parser.error("기존 보고서를 덮어쓰지 않음. 다른 --output을 지정하세요")
    try:
        report = run(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except Exception as exc:
        parser.exit(1, f"실행 검증 실패: {exc}\n")
    print(json.dumps({"output": str(args.output), "http": report["http"],
                      "inference": report["inference"], "concurrency": report["concurrency"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
