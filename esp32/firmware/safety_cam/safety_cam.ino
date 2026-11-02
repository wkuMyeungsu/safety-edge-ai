// safety_cam: XIAO ESP32S3 Sense가 카메라 프레임에서 사람을 감지하면 그 프레임의 JPEG를 pi gateway로 보낸다.
// 카메라 한 장(QVGA JPEG) → 모델 입력 크기 RGB로 줄임 → Edge Impulse FOMO 사람 감지 → 사람 박스가 연속으로 보이면 POST.
// 라이브러리: esp32/model/의 Edge Impulse .zip을 Sketch → Include Library → Add .ZIP Library로 설치.
// 설정: config.example.h를 config.h로 복사해 Wi-Fi와 gateway 주소를 채운다.

#include <Person_detection_FOMO_3_inferencing.h>
#include "edge-impulse-sdk/dsp/image/image.hpp"
#include "esp_camera.h"
#include "esp_memory_utils.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include "config.h"

// 펌웨어를 바꿀 때마다 올린다 (CLAUDE.md 6절)
#define FW_VERSION "0.3.1"

// ================= 설정 =================
const char* PERSON_LABEL           = "hum";  // 모델에서 사람을 뜻하는 라벨 (Edge Impulse 라벨과 같아야 한다)
const float PERSON_THRESHOLD       = 0.5f;   // 사람 박스로 칠 최소 점수. 모델 자체 threshold(0.5) 아래 박스는 모델이 이미 버린다
const int   CONFIRM_FRAMES         = 2;      // 연속 N프레임 감지해야 전송 (순간 오탐 제거)
const unsigned long COOLDOWN_MS    = 5000;   // 전송 후 다음 전송까지 대기
const unsigned long WIFI_RETRY_MS  = 5000;   // Wi-Fi 끊겼을 때 재연결 간격
const uint16_t HTTP_TIMEOUT_MS     = 5000;
const bool  PRINT_BOXES            = false;  // 박스 좌표까지 시리얼에 출력
// ========================================

// XIAO ESP32S3 Sense 카메라 핀 (camera_pins.h의 CAMERA_MODEL_XIAO_ESP32S3)
#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  10
#define SIOD_GPIO_NUM  40
#define SIOC_GPIO_NUM  39
#define Y9_GPIO_NUM    48
#define Y8_GPIO_NUM    11
#define Y7_GPIO_NUM    12
#define Y6_GPIO_NUM    14
#define Y5_GPIO_NUM    16
#define Y4_GPIO_NUM    18
#define Y3_GPIO_NUM    17
#define Y2_GPIO_NUM    15
#define VSYNC_GPIO_NUM 38
#define HREF_GPIO_NUM  47
#define PCLK_GPIO_NUM  13
#define LED_PIN        21  // 사용자 LED (LOW = 켜짐). 사람이 보이면 켠다

// 카메라는 QVGA JPEG로 찍고 RGB888로 풀어 모델 입력 크기로 줄인다
#define RAW_COLS 320
#define RAW_ROWS 240
#define RAW_BPP  3
#define JPEG_MAX_BYTES (64 * 1024)  // 전송용 JPEG 복사본 크기 상한. QVGA·quality 12는 보통 10~20KB

#if !defined(EI_CLASSIFIER_SENSOR) || EI_CLASSIFIER_SENSOR != EI_CLASSIFIER_SENSOR_CAMERA
#error "카메라용 모델이 아니다"
#endif
#if EI_CLASSIFIER_OBJECT_DETECTION != 1
#error "물체 감지(FOMO) 모델용 스케치다. 분류 모델이면 result.classification으로 판정을 바꾼다"
#endif

struct PersonResult {
  bool person;       // PERSON_THRESHOLD를 넘은 사람 박스가 하나라도 있으면 true
  float score;       // 가장 높은 사람 박스 점수 (없으면 0)
  int count;         // PERSON_THRESHOLD를 넘은 사람 박스 수
  uint32_t inferMs;  // 전처리(DSP) + 모델 실행 시간
};

// Edge Impulse 라이브러리의 ei_calloc(weak)을 바꿔 끼운다. 두 가지를 고친다.
// 1) ESP32-S3 가속(ESP-NN)은 임시 버퍼가 16바이트 정렬이라고 가정하는데, 라이브러리는 ESP-IDF 5(esp32 코어 3.x)에서
//    정렬 없이 할당해 버퍼 밖을 덮어쓰고 CORRUPT HEAP으로 재부팅된다.
// 2) 모델 메모리(tensor arena)가 PSRAM에 잡히면 추론이 몇 배 느려진다. 내부 RAM에 먼저 잡고, 모자라면 PSRAM에 잡는다.
// 해제는 라이브러리의 ei_free(= free)가 그대로 한다. (Arduino가 첫 함수 앞에 선언을 끼우므로 struct 뒤에 둔다)
void* ei_calloc(size_t nitems, size_t size) {
  void* p = heap_caps_aligned_calloc(16, nitems, size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  if (!p) p = heap_caps_aligned_calloc(16, nitems, size, MALLOC_CAP_DEFAULT);
  if (p && nitems * size >= 16 * 1024) {
    Serial.printf("[mem] 모델 버퍼 %u bytes → %s\n", (unsigned)(nitems * size),
                  esp_ptr_external_ram(p) ? "PSRAM (느림)" : "내부 RAM");
  }
  return p;
}

static uint8_t* snapshotBuf = nullptr;  // RAW_COLS×RAW_ROWS×3, PSRAM. 리사이즈 후 앞부분이 모델 입력이 된다
static uint8_t* jpegBuf = nullptr;      // 추론한 프레임의 JPEG 복사본, PSRAM. 감지되면 이것을 보낸다
static size_t jpegLen = 0;

static int consecutiveHits = 0;
static unsigned long lastSent = 0;
static unsigned long lastWifiTry = 0;

bool initCamera() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer   = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM;  c.pin_d1 = Y3_GPIO_NUM;
  c.pin_d2 = Y4_GPIO_NUM;  c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM;  c.pin_d5 = Y7_GPIO_NUM;
  c.pin_d6 = Y8_GPIO_NUM;  c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk     = XCLK_GPIO_NUM;
  c.pin_pclk     = PCLK_GPIO_NUM;
  c.pin_vsync    = VSYNC_GPIO_NUM;
  c.pin_href     = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM;
  c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn     = PWDN_GPIO_NUM;
  c.pin_reset    = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size   = FRAMESIZE_QVGA;
  c.jpeg_quality = 12;
  c.fb_count     = 1;
  c.fb_location  = CAMERA_FB_IN_PSRAM;
  c.grab_mode    = CAMERA_GRAB_LATEST;  // 추론하는 동안 쌓인 오래된 프레임 대신 최신 프레임

  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("[cam] 초기화 실패 0x%x\n", err);
    return false;
  }
  sensor_t* s = esp_camera_sensor_get();
  if (s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);       // OV3660은 위아래가 뒤집혀 나온다
    s->set_brightness(s, 1);
    s->set_saturation(s, 0);
  }
  return true;
}

// 카메라 한 장 → jpegBuf에 원본 JPEG, snapshotBuf 앞부분에 EI_CLASSIFIER_INPUT_WIDTH×HEIGHT RGB888
bool captureFrame() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[cam] 촬영 실패");
    return false;
  }
  // 추론한 바로 그 프레임을 보내려고 JPEG를 복사해 둔다. 너무 크면 이번 프레임은 전송하지 않는다
  if (fb->len <= JPEG_MAX_BYTES) {
    memcpy(jpegBuf, fb->buf, fb->len);
    jpegLen = fb->len;
  } else {
    jpegLen = 0;
  }
  bool ok = fmt2rgb888(fb->buf, fb->len, PIXFORMAT_JPEG, snapshotBuf);
  esp_camera_fb_return(fb);
  if (!ok) {
    Serial.println("[cam] JPEG 변환 실패");
    return false;
  }
  // Edge Impulse 학습 때와 같은 방식(EI_CLASSIFIER_RESIZE_MODE)으로 모델 입력 크기로 줄인다.
  // 지금 모델은 fit longest: 화면 전체를 줄이고 위아래 남는 곳을 검게 채운다
  ei::image::processing::resize_image_using_mode(
      snapshotBuf, RAW_COLS, RAW_ROWS,
      snapshotBuf, EI_CLASSIFIER_INPUT_WIDTH, EI_CLASSIFIER_INPUT_HEIGHT,
      RAW_BPP, EI_CLASSIFIER_RESIZE_MODE);
  return true;
}

// Edge Impulse가 입력을 읽어 가는 콜백. 픽셀 하나를 0xRRGGBB 정수(float)로 넘긴다
static int getSignalData(size_t offset, size_t length, float* out) {
  size_t px = offset * 3;
  for (size_t i = 0; i < length; i++, px += 3) {
    // fmt2rgb888은 BGR 순서로 쓴다 (esp32-camera#379)
    out[i] = (snapshotBuf[px + 2] << 16) + (snapshotBuf[px + 1] << 8) + snapshotBuf[px];
  }
  return 0;
}

// 한 장 찍어 모델을 돌린다. 실패하면 false
bool runPersonModel(PersonResult& out) {
  if (!captureFrame()) return false;

  ei::signal_t signal;
  signal.total_length = EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT;
  signal.get_data = &getSignalData;

  ei_impulse_result_t result = {};
  EI_IMPULSE_ERROR err = run_classifier(&signal, &result, false);
  if (err != EI_IMPULSE_OK) {
    Serial.printf("[model] 실행 실패 (%d)\n", err);
    return false;
  }

  out = {false, 0.0f, 0, (uint32_t)(result.timing.dsp + result.timing.classification)};
  for (uint32_t i = 0; i < result.bounding_boxes_count; i++) {
    const ei_impulse_result_bounding_box_t& bb = result.bounding_boxes[i];
    if (bb.value < PERSON_THRESHOLD || strcmp(bb.label, PERSON_LABEL) != 0) continue;
    out.count++;
    if (bb.value > out.score) out.score = bb.value;
    if (PRINT_BOXES) {
      Serial.printf("  %s %.2f [x=%u y=%u w=%u h=%u]\n", bb.label, bb.value, bb.x, bb.y, bb.width, bb.height);
    }
  }
  out.person = out.count > 0;
  return true;
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // 전송 응답성
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[wifi] 연결 중");
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[wifi] 연결됨 %s (RSSI %d dBm)\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("\n[wifi] 실패, loop에서 다시 시도");
  }
  lastWifiTry = millis();
}

// 끊겼으면 WIFI_RETRY_MS마다 재연결을 건다. 기다리지 않으므로 감지는 계속 돈다
void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - lastWifiTry < WIFI_RETRY_MS) return;
  lastWifiTry = millis();
  Serial.println("[wifi] 끊김, 재연결");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

// jpegBuf(감지된 프레임)를 gateway로 보낸다. 2xx(gateway는 202 queued)면 true.
// 400·413·503은 재시도하지 않고 버린다 (docs/contracts/frame.md). 본문의 detail은 아래 로그에 그대로 찍힌다
bool sendFrame(const PersonResult& r) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[http] Wi-Fi 없음, 전송 건너뜀");
    return false;
  }
  if (jpegLen == 0) {
    Serial.println("[http] JPEG가 너무 커서 전송 건너뜀");
    return false;
  }
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.begin(GATEWAY_URL);
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Device-Id", DEVICE_ID);
  http.addHeader("X-Person-Score", String(r.score, 2));
  http.addHeader("X-Person-Count", String(r.count));
  unsigned long t0 = millis();
  int code = http.POST(jpegBuf, jpegLen);
  Serial.printf("[http] POST -> %d (%u bytes, %lu ms) %s\n",
                code, (unsigned)jpegLen, millis() - t0, code > 0 ? http.getString().c_str() : "");
  http.end();
  return code >= 200 && code < 300;
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.printf("FW_VERSION %s\n", FW_VERSION);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);

  Serial.printf("[boot] model=%s 입력 %dx%d, label=%s, threshold=%.2f, confirm=%d, cooldown=%lums\n",
                EI_CLASSIFIER_PROJECT_NAME, EI_CLASSIFIER_INPUT_WIDTH, EI_CLASSIFIER_INPUT_HEIGHT,
                PERSON_LABEL, PERSON_THRESHOLD, CONFIRM_FRAMES, COOLDOWN_MS);
  bool labelFound = false;
  for (int i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
    if (strcmp(ei_classifier_inferencing_categories[i], PERSON_LABEL) == 0) labelFound = true;
  }
  if (!labelFound) {
    Serial.printf("[boot] 모델 라벨에 \"%s\"이 없다. PERSON_LABEL을 Edge Impulse 라벨과 맞춘다\n", PERSON_LABEL);
    while (true) delay(1000);
  }

  if (!psramFound()) {
    Serial.println("[boot] PSRAM 없음. Tools → PSRAM → OPI PSRAM으로 바꾼다");
    while (true) delay(1000);
  }
  snapshotBuf = (uint8_t*)ps_malloc(RAW_COLS * RAW_ROWS * RAW_BPP);
  jpegBuf = (uint8_t*)ps_malloc(JPEG_MAX_BYTES);
  if (!snapshotBuf || !jpegBuf || !initCamera()) {
    Serial.println("[boot] 초기화 실패, 재부팅");
    delay(1000);
    ESP.restart();
  }

  connectWiFi();
  Serial.printf("[boot] 준비됨, gateway=%s device=%s\n", GATEWAY_URL, DEVICE_ID);
}

void loop() {
  ensureWiFi();

  PersonResult r;
  if (!runPersonModel(r)) {
    delay(100);
    return;
  }
  digitalWrite(LED_PIN, r.person ? LOW : HIGH);
  Serial.printf("person=%s score=%.2f count=%d infer_ms=%u\n", r.person ? "true" : "false", r.score, r.count, r.inferMs);

  // 연속 프레임 확인 → 쿨다운 → 전송
  consecutiveHits = r.person ? consecutiveHits + 1 : 0;
  if (consecutiveHits >= CONFIRM_FRAMES && millis() - lastSent > COOLDOWN_MS) {
    Serial.printf(">> 사람 확인 (%.2f, %d명), 전송\n", r.score, r.count);
    sendFrame(r);
    lastSent = millis();  // 실패해도 쿨다운을 건다 (gateway가 죽었을 때 매 프레임 재시도 방지)
    consecutiveHits = 0;
  }
}
