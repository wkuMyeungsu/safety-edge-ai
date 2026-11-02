"""서버와 PC 검증 도구가 공통으로 확인하는 YOLOv8 ONNX 형식."""

import ast

from detector import categorize


def inspect_session(session):
    metadata = session.get_modelmeta().custom_metadata_map
    names = ast.literal_eval(metadata.get("names", "[]"))
    if isinstance(names, dict):
        if set(names) != set(range(len(names))):
            raise ValueError("클래스 번호는 0부터 빈틈없이 이어져야 함")
        names = [names[i] for i in range(len(names))]
    if (not isinstance(names, list) or not names
            or any(not isinstance(name, str) or not name.strip() for name in names)
            or len(set(names)) != len(names)):
        raise ValueError("names 메타데이터에 서로 다른 클래스 이름이 필요함")
    if metadata.get("task", "detect") != "detect":
        raise ValueError("객체 검출(detect) 모델만 지원함")

    categories = {names[i]: category for i, category in categorize(names).items()}
    found = set(categories.values())
    if not ({"helmet", "no_helmet"} & found and {"vest", "no_vest"} & found):
        raise ValueError(f"안전모·조끼를 판정할 수 없는 모델: 클래스 {names}")

    inputs, outputs = session.get_inputs(), session.get_outputs()
    if len(inputs) != 1 or len(outputs) != 1:
        raise ValueError("입력 1개와 NMS 전 검출 출력 1개가 필요함")
    inp, out = inputs[0], outputs[0]
    shape = inp.shape
    if (inp.type != "tensor(float)" or len(shape) != 4 or shape[:2] != [1, 3]
            or not isinstance(shape[2], int) or shape[2] <= 0 or shape[2] != shape[3]):
        raise ValueError(f"입력은 고정 크기 float32 [1, 3, S, S]여야 함: {inp.type} {shape}")
    shape = out.shape
    if (out.type != "tensor(float)" or len(shape) != 3 or shape[:2] != [1, 4 + len(names)]
            or not isinstance(shape[2], int) or shape[2] <= 0):
        raise ValueError(f"출력은 float32 [1, {4 + len(names)}, N]이어야 함 (NMS 제외): {out.type} {shape}")
    return inp.name, inp.shape[2], names, categories
