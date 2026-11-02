// 뼈대: Wi-Fi 연결만 한다. 사람 감지와 전송은 esp32 담당자가 채운다.
#include <WiFi.h>
#include "config.h"

void setup() {
  Serial.begin(115200);
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
