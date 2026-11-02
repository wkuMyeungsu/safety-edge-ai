"""POST /predict의 입력 검사와 오류 코드 (docs/contracts/inference.md '오류'). 모델 없이도 돈다."""

import base64

import pytest
import requests

# 16×16 회색 JPEG (629바이트). 모델 없이도 "읽을 수 있는 JPEG"로 쓴다
TINY_JPEG = base64.b64decode("/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAAQABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwAooooA/9k=")
JPEG = {"Content-Type": "image/jpeg"}


def predict(url, body):
    return requests.post(f"{url}/predict", data=body, headers=JPEG, timeout=10)


def test_empty_body_is_400(inference_url):
    r = predict(inference_url, b"")
    assert r.status_code == 400
    assert r.json()["detail"]


def test_not_a_jpeg_is_400(inference_url):
    r = predict(inference_url, b"this is not an image")
    assert r.status_code == 400


def test_over_2mb_is_413(inference_url):
    r = predict(inference_url, TINY_JPEG + b"\0" * (2 * 1024 * 1024))
    assert r.status_code == 413


def test_without_model_is_503(inference_url):
    if requests.get(f"{inference_url}/health", timeout=5).json()["model_loaded"]:
        pytest.skip("모델이 있어 503 상황이 아님")
    r = predict(inference_url, TINY_JPEG)
    assert r.status_code == 503
    assert "모델" in r.json()["detail"]
