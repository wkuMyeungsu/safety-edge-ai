"""요청이 몰려도 /health가 응답하고 추론 결과가 섞이지 않아야 한다."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
import requests


@pytest.mark.model
def test_health_during_parallel_predictions(inference_url, image_bytes):
    photo = image_bytes("blank.jpg")
    clients = 48
    ready = Barrier(clients + 1)

    def predict():
        ready.wait(timeout=15)
        return requests.post(f"{inference_url}/predict", data=photo,
                             headers={"Content-Type": "image/jpeg"}, timeout=60)

    with ThreadPoolExecutor(max_workers=clients) as pool:
        pending = [pool.submit(predict) for _ in range(clients)]
        ready.wait(timeout=15)
        time.sleep(0.3)  # 요청들이 서버의 추론 대기에 들어갈 시간을 준다.
        assert any(not task.done() for task in pending), "동시 요청 중 상태 확인을 해야 함"
        health = requests.get(f"{inference_url}/health", timeout=1)
        assert health.status_code == 200
        assert health.json()["model_loaded"] is True
        for task in pending:
            response = task.result()
            assert response.status_code == 200, response.text
            assert response.json()["verdict"] == "no_person"
