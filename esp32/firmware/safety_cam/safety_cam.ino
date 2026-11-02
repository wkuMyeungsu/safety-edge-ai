// 뼈대: Wi-Fi 연결만 한다. 사람 감지와 전송은 esp32 담당자가 채운다.
#include <WiFi.h>
#include "config.h"

// 펌웨어를 바꿀 때마다 올린다 (CLAUDE.md 6절)
#define FW_VERSION "0.1.0"

void setup() {
  Serial.begin(115200);
  Serial.printf("FW_VERSION %s\n", FW_VERSION);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWi-Fi connected: %s\n", WiFi.localIP().toString().c_str());
}

void loop() {
  delay(1000);
}
