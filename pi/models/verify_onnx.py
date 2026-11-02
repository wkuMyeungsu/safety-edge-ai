"""ONNX 구조·메타데이터·실행 결과 확인. PC/Pi에서 torch 없이도 실행 가능."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "inference"))
from model_spec import inspect_session  # noqa: E402


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(path, expected_sha256=None):
    path = Path(path)
    digest = sha256(path)
    if expected_sha256 and digest != expected_sha256.lower():
        raise ValueError(f"SHA256 불일치: 기대 {expected_sha256}, 실제 {digest}")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 3
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
    input_name, size, classes, _ = inspect_session(session)
    output = session.run(None, {input_name: np.zeros((1, 3, size, size), dtype=np.float32)})[0]
    if not np.isfinite(output).all():
        raise ValueError("출력에 NaN 또는 무한대가 있음")
    if np.any(output[:, 4:, :] < 0) or np.any(output[:, 4:, :] > 1):
        raise ValueError("클래스 점수가 0~1 범위를 벗어남")
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": digest,
            "input": session.get_inputs()[0].shape, "output": list(output.shape),
            "classes": classes, "onnxruntime": ort.__version__, "provider": "CPUExecutionProvider"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--sha256", help="배포한 모델의 SHA256과 비교")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.model, args.sha256), ensure_ascii=False, indent=2))
    except Exception as exc:
        parser.exit(1, f"검증 실패: {exc}\n")


if __name__ == "__main__":
    main()
