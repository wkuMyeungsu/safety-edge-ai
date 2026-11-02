"""PC에서 검증된 원본 가중치를 정적 FP32 ONNX로 변환하고 수치 일치를 검사한다."""

import argparse
import json
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path

from verify_onnx import sha256, verify

SOURCES = {
    "hansung": {
        "repo": "Hansung-Cho/yolov8-ppe-detection",
        "revision": "ac0027bd38bc619d5ce4f52b4cc01beb87d8b958",
        "sha256": "2419700bbe3b8d38f9000655d9cf952a4bc93ef6c143baf8b49a0abde5d0760f",
    },
    "safesight": {
        "repo": "killuminati1/construction-ppe-yolov8",
        "revision": "06ce70134a78f31881e2f9a223719d60a0a9a6a9",
        "sha256": "31ef3ca04a17cf545f3fcfc64c4af8993a41d52ccc460e82aff01d5354603533",
    },
}
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--download", action="store_true", help="문서의 후보 모델을 고정 revision에서 받기")
    source.add_argument("--weights", type=Path, help="같은 원본 best.pt의 로컬 경로 (SHA256 필수 확인)")
    parser.add_argument("--source", choices=SOURCES, default="hansung", help="검증할 원본 후보 (기본 hansung)")
    parser.add_argument("--output", type=Path, default=HERE / "ppe_yolov8.onnx")
    args = parser.parse_args()
    selected = SOURCES[args.source]
    source_url = f"https://huggingface.co/{selected['repo']}/resolve/{selected['revision']}/best.pt"
    output = args.output.resolve()
    if output.exists():
        parser.error("출력 파일이 이미 있음. 기존 배포본을 보존하고 다른 --output 경로를 지정하세요")
    output.parent.mkdir(parents=True, exist_ok=True)
    os.environ["YOLO_AUTOINSTALL"] = "false"
    with tempfile.TemporaryDirectory(prefix="ppe-export-", dir=output.parent) as temporary:
        weights = Path(temporary) / "best.pt"
        if args.download:
            with urllib.request.urlopen(source_url, timeout=60) as response, weights.open("wb") as target:
                shutil.copyfileobj(response, target)
        else:
            shutil.copyfile(args.weights, weights)
        if sha256(weights) != selected["sha256"]:
            parser.error("원본 best.pt SHA256 불일치. 가중치를 불러오지 않았습니다")

        import numpy as np
        import onnx
        import onnxruntime as ort
        import torch
        import ultralytics
        from ultralytics import YOLO

        torch.set_num_threads(3)
        model = YOLO(str(weights), task="detect")
        exported = Path(model.export(format="onnx", imgsz=640, batch=1, dynamic=False, half=False,
                                     simplify=False, nms=False, opset=17, device="cpu"))
        onnx.checker.check_model(str(exported))
        report = verify(exported)
        # 같은 입력과 같은 fused graph를 비교한다. 사진별 정확도 검사는 별도 HTTP 테스트에서 한다.
        reference = YOLO(str(weights), task="detect").model.cpu().float().eval().fuse()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 3
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(exported), options, providers=["CPUExecutionProvider"])
        rng = np.random.default_rng(0)
        errors = []
        for blob in (np.zeros((1, 3, 640, 640), dtype=np.float32),
                     rng.random((1, 3, 640, 640), dtype=np.float32)):
            with torch.inference_mode():
                expected = reference(torch.from_numpy(blob))[0].numpy()
            actual = session.run(None, {session.get_inputs()[0].name: blob})[0]
            np.testing.assert_allclose(actual, expected, rtol=1e-3, atol=1e-3)
            errors.append(float(np.max(np.abs(actual - expected))))
        report.update(file=output.name, source_url=source_url, source_revision=selected["revision"],
                      source_sha256=selected["sha256"], ultralytics=ultralytics.__version__,
                      torch=torch.__version__, onnx=onnx.__version__, opset=17,
                      parity_max_abs_errors=errors, parity_rtol=1e-3, parity_atol=1e-3)
        shutil.copyfile(exported, output)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
