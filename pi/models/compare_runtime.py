"""로컬 실제 HTTP 서버를 순차 실행하여 ORT 설정 6종의 시간과 사진 판정을 비교한다."""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from run_http_smoke import ROOT, request_json, run


def compare(args):
    reports = []
    for threads, spinning in ((3, "1"), (3, "0"), (2, "0"), (1, "0"), (1, "1"), (2, "1")):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {**os.environ, "MODEL_PATH": str(args.model.resolve()),
               "ORT_THREADS": str(threads), "ORT_SPINNING": spinning}
        url = f"http://127.0.0.1:{port}"
        with tempfile.TemporaryFile(mode="w+") as logs:
            process = subprocess.Popen(
                [str(args.python.resolve()), "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=ROOT / "pi/inference", env=env, stdin=subprocess.DEVNULL, stdout=logs, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                deadline = time.monotonic() + 60
                while True:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("비교 서버 시작 실패")
                    try:
                        health, _ = request_json(url + "/health", timeout=1)
                    except OSError:
                        time.sleep(0.1)
                        continue
                    if not health.get("model_loaded"):
                        raise ValueError(f"모델 로드 실패: {health}")
                    break
                report = run(SimpleNamespace(
                    url=url, model=args.model, manifest=args.manifest, repeats=args.repeats, parallel=2,
                    server_label=f"{args.server_label}; native; ORT_THREADS={threads}; ORT_SPINNING={spinning}",
                ))
                report["runtime_settings"] = {"ort_threads": threads, "ort_spinning": spinning}
                reports.append(report)
                print(json.dumps({"settings": report["runtime_settings"], "inference": report["inference"]}), flush=True)
            except Exception:
                logs.seek(0)
                print(logs.read()[-4000:], file=sys.stderr)
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
    # 시간을 제외한 응답을 비교한다. 반올림한 점수·좌표·인원 수도 같아야 한다.
    def predictions(report):
        return {case["image"]: {key: value for key, value in case["prediction"].items() if key != "infer_ms"}
                for case in report["cases"]}

    baseline = predictions(reports[0])
    if any(predictions(report) != baseline for report in reports[1:]):
        raise ValueError("설정 사이에서 시간을 제외한 판정 JSON이 달라짐")
    return {"comparison": "same model file and input shape; sequential native HTTP servers; all 6 runtime settings",
            "exact_prediction_parity_excluding_infer_ms": True,
            "parity_note": "각 사진의 예열 응답을 비교함. 각 설정의 모든 측정·동시 요청 응답은 expected.json과도 대조함.",
            "reports": reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="추론 의존성이 설치된 Python")
    parser.add_argument("--model", type=Path, default=ROOT / "pi/models/ppe_yolov8.onnx")
    parser.add_argument("--manifest", type=Path, default=ROOT / "pi/models/model-v1.json")
    parser.add_argument("--server-label", required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.repeats <= 100:
        parser.error("새 출력 경로와 1~100 사이 repeats를 지정하세요")
    try:
        report = compare(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except Exception as exc:
        parser.exit(1, f"런타임 비교 실패: {exc}\n")
    print(f"설정 6종의 기대 판정 및 응답 동일성 확인: {args.output}")


if __name__ == "__main__":
    main()
