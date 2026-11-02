# tests

담당자는 자기 파트 폴더에 `test_*.py`를 추가한다. CI 파일은 고치지 않아도 된다.

| 폴더 | 담당 | 언제 CI에서 도는가 |
|---|---|---|
| `esp32/` | esp32 | `esp32/` 또는 `tests/esp32/`가 바뀐 PR |
| `pi/gateway/` `pi/inference/` `pi/uploader/` | pi (하위 폴더 담당) | `pi/` 또는 `tests/pi/`가 바뀐 PR |
| `cloud/` | cloud | `cloud/` 또는 `tests/cloud/`가 바뀐 PR |
| `contracts/` | 공통 | `docs/contracts/`·`tests/contracts/`가 바뀌면 모든 job이 돈다 |
| `e2e/` | 공통 | pi job과 함께 |
| `fixtures/images/` | 공통 | 테스트 사진 (한 장 수백 KB 이하) |

- 테스트는 서비스 코드를 import하지 않고, 실행 중인 컨테이너에 HTTP로 요청한다. 주소는 `conftest.py`의 fixture(`gateway_url` 등)를 쓴다.
- 실제 모델이 필요한 테스트는 `@pytest.mark.model`을 붙인다. `pi/models/ppe_yolov8.onnx`가 없으면 건너뛴다.
- Supabase가 필요한 테스트는 `@pytest.mark.supabase`, Pi에서만 의미 있는 측정은 `@pytest.mark.pi`.

## 내 PC에서 돌리기

```bash
cd pi
docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build --wait
cd ..
pip install -r tests/requirements.txt
pytest tests/pi -m "not pi and not supabase"
```

Pi에서 측정: `pytest -m pi`
