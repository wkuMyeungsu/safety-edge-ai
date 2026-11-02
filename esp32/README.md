# esp32

XIAO ESP32-S3가 카메라 프레임에서 사람을 감지하면, 그 프레임의 JPEG를 pi gateway로 보낸다.

| 폴더 | 내용 |
|---|---|
| `model/` | Edge Impulse 사람 감지 모델 정보. 내려받은 Arduino 라이브러리 zip은 커밋하지 않는다. |
| `firmware/safety_cam/` | Arduino 스케치. `config.example.h`를 `config.h`로 복사해 Wi-Fi와 pi 주소를 채운다. |
