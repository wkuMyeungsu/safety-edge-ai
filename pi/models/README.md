# 모델 파일

`*.onnx`, `*.pt`는 커밋하지 않는다. 받는 법과 확인값을 이 표에 기록한다.

| 파일 | 출처 | 변환 방법 | SHA256 |
|---|---|---|---|
| `ppe_yolov8.onnx` | https://huggingface.co/Hansung-Cho/yolov8-ppe-detection (사용 여부 미정) | 미정 | 미정 |

SHA256 확인: `sha256sum ppe_yolov8.onnx`

변환한 ONNX는 GitHub Release `model-v1`에 첨부한다. CI는 그 파일을 받아 `@pytest.mark.model` 테스트에 쓰고, 이 README가 바뀌기 전까지 캐시에서 다시 쓴다. 모델을 바꾸면 Release를 새로 올리고 이 표를 고친다.

```bash
gh release create model-v1 pi/models/ppe_yolov8.onnx --title "PPE 모델 v1" --notes "출처·변환 방법은 pi/models/README.md"
```
