# PPE 회귀 테스트 사진

출처: [Roboflow Universe Projects — Construction Site Safety Dataset v1](https://universe.roboflow.com/roboflow-universe-projects/construction-site-safety/dataset/1), 2023년 1월.
배포본: [keremberke/construction-safety-object-detection](https://huggingface.co/datasets/keremberke/construction-safety-object-detection), revision `a19eace121442bce60da9f5036dc16bf9f2f6fa6`, `full` 구성의 `test` split.
라이선스: 배포본의 Dataset Card에 표시된 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Hugging Face Dataset Viewer가 제공하는 JPEG 바이트를 변경 없이 저장했다. 파일 이름은 원본 `image_id`다. 모델 실행 전에 원본 라벨과 사진을 확인해 아래 기대값을 정했다.

| 파일 | test 행 번호(0부터) | 원본 PPE 라벨 | 기대 판정 |
|---|---:|---|---|
| `test_11.jpg` | 2 | hardhat, safety vest, person | pass, 안전모 true, 조끼 true |
| `test_0.jpg` | 16 | no-hardhat, no-safety vest, person | fail, 안전모 false, 조끼 false |
| `test_26.jpg` | 26 | hardhat, no-safety vest, person | fail, 안전모 true, 조끼 false |

SHA256:

```text
54fb5c995fa8dd68c6e7b94922edc4928f9872767a1d8ca7f5a1cef320c0df29  test_11.jpg
5a420857d72a054e3b0f65d54c3bc298b8494bdd4a7a9f6f89ba2cd25dba6156  test_0.jpg
6bf50e73ec9a1064336286050ebd1473e60d850bed741bfd7eaf69911e6d2e24  test_26.jpg
```

이 3장은 판정 코드·배포 모델의 회귀 검사다. 학습 데이터와의 중복 여부를 확인하지 않았으므로 독립 테스트셋의 정확도나 현장 성능으로 해석하지 않는다. 기존 공통 사진 `blank.jpg`는 사람이 없는 경우를 확인한다.

## 입력 경계용 이미지

`thin_landscape.jpg`(4096×1), `thin_portrait.jpg`(1×4096)는 모든 RGB 값이 114인 배열을 OpenCV 4.10.0으로 JPEG 인코딩해 직접 만든 회색 이미지다. 외부 사진을 사용하지 않았다. 매우 긴 JPEG를 축소할 때 한쪽 길이가 0이 되어 발생하던 500 오류를 검사한다. 실제 사진의 판정 정확도 집계에는 포함하지 않는다.
