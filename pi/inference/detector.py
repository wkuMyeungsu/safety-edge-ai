"""YOLOv8 PPE ONNX 결과를 해석해 안전모·조끼 착용을 판정한다 (docs/contracts/inference.md "판정 규칙").

ultralytics YOLOv8 ONNX 출력: [1, 4 + 클래스 수, N]. 각 열 = (cx, cy, w, h, 클래스별 점수...), 입력(정사각형) 기준 좌표.
"""

import re

import cv2
import numpy as np

# 클래스 이름 → 종류. 이름은 소문자로 바꾸고 영문·숫자만 남겨 비교한다 ("NO-Safety Vest" → "nosafetyvest")
CATEGORY_NAMES = {
    "person": {"person", "worker", "people"},
    "helmet": {"hardhat", "helmet", "safetyhelmet"},
    "no_helmet": {"nohardhat", "nohelmet", "head"},  # "head": 안전모 없이 드러난 머리를 따로 학습한 데이터셋
    "vest": {"safetyvest", "vest", "reflectivevest"},
    "no_vest": {"nosafetyvest", "novest"},
}


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def categorize(classes: list[str]) -> dict[int, str]:
    """클래스 번호 → 종류 (판정에 쓰지 않는 클래스는 빠진다)."""
    out = {}
    for i, name in enumerate(classes):
        for category, names in CATEGORY_NAMES.items():
            if normalize(name) in names:
                out[i] = category
    return out


def letterbox(image: np.ndarray, size: int):
    """비율을 지키며 size×size에 맞추고 남는 곳은 회색(114)으로 채운다 (ultralytics와 같은 방식)."""
    h, w = image.shape[:2]
    r = min(size / h, size / w)
    # 매우 긴 JPEG도 반대쪽 변이 0으로 반올림되지 않게 한다.
    nw, nh = max(1, round(w * r)), max(1, round(h * r))
    dw, dh = (size - nw) / 2, (size - nh) / 2
    resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR) if (nw, nh) != (w, h) else image
    top, left = round(dh - 0.1), round(dw - 0.1)
    padded = cv2.copyMakeBorder(resized, top, size - nh - top, left, size - nw - left, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return padded, r, left, top


def preprocess(image_bgr: np.ndarray, size: int):
    padded, r, left, top = letterbox(image_bgr, size)
    blob = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    return np.ascontiguousarray(blob), r, left, top


def decode(output: np.ndarray, classes: list[str], r: float, left: int, top: int, width: int, height: int,
           conf_thres: float, iou_thres: float) -> list[dict]:
    """[1, 4+nc, N] → 점수 기준과 NMS(클래스별)를 거친 검출 목록. box는 원본 사진 픽셀 [x1, y1, x2, y2]."""
    pred = output[0].T  # [N, 4+nc]
    scores_all = pred[:, 4:]
    cls = scores_all.argmax(axis=1)
    score = scores_all[np.arange(len(pred)), cls]
    keep = score >= conf_thres
    pred, cls, score = pred[keep], cls[keep], score[keep]
    if not len(pred):
        return []
    cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    x1 = np.clip((cx - w / 2 - left) / r, 0, width)
    y1 = np.clip((cy - h / 2 - top) / r, 0, height)
    x2 = np.clip((cx + w / 2 - left) / r, 0, width)
    y2 = np.clip((cy + h / 2 - top) / r, 0, height)
    detections = []
    for c in np.unique(cls):
        idx = np.where(cls == c)[0]
        rects = [[float(x1[i]), float(y1[i]), float(x2[i] - x1[i]), float(y2[i] - y1[i])] for i in idx]
        kept = cv2.dnn.NMSBoxes(rects, score[idx].tolist(), conf_thres, iou_thres)
        for k in np.array(kept).flatten():
            i = idx[int(k)]
            name = classes[c] if c < len(classes) else str(int(c))
            detections.append({"label": name, "score": round(float(score[i]), 3),
                               "box": [int(round(x1[i])), int(round(y1[i])), int(round(x2[i])), int(round(y2[i]))]})
    return sorted(detections, key=lambda d: d["score"], reverse=True)


def judge(detections: list[dict], categories_by_label: dict[str, str]) -> dict:
    """검출 → verdict, has_helmet, has_vest, confidence, persons (계약의 판정 규칙 1~4)."""
    groups = {k: [] for k in CATEGORY_NAMES}
    for d in detections:
        category = categories_by_label.get(d["label"])
        if category:
            groups[category].append(d["score"])
    persons = len(groups["person"])
    # 사람 검출을 놓쳐도 안전모·조끼 관련 검출 수로 사람 수를 짐작한다
    people = max(persons, len(groups["helmet"]) + len(groups["no_helmet"]), len(groups["vest"]) + len(groups["no_vest"]))
    if people == 0:
        return {"verdict": "no_person", "has_helmet": True, "has_vest": True, "confidence": 0.0, "persons": 0}
    has_helmet = not groups["no_helmet"] and len(groups["helmet"]) >= people
    has_vest = not groups["no_vest"] and len(groups["vest"]) >= people
    if has_helmet and has_vest:
        verdict, evidence = "pass", groups["helmet"] + groups["vest"]
    else:
        verdict = "fail"
        evidence = (groups["no_helmet"] if not has_helmet else []) + (groups["no_vest"] if not has_vest else [])
        evidence = evidence or groups["person"] or groups["helmet"] + groups["vest"]  # 미착용 검출 없이 개수가 모자란 경우
    return {"verdict": verdict, "has_helmet": has_helmet, "has_vest": has_vest,
            "confidence": round(max(evidence), 3) if evidence else 0.0, "persons": people}
