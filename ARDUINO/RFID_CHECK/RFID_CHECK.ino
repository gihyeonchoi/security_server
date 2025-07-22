/*
ESP32 D1 R32 BOARD 기준
SDA    : IO 5
SCK    : IO 18
MOSI  : IO 23
MISO  : IO 19
RST     : IO 13

*/

// RFID 라이브러리
#include <SPI.h>
#include <MFRC522.h>
// JSON 사용 라이브러리
#include <ArduinoJson.h>
#include <ArduinoJson.hpp>
// HTTP 연결 라이브러리
#include <HTTPClient.h>
// WiFi 연결 매니저 라이브러리
#include "WiFiConfigManager.h"
// #include "WiFiConfigManager.cpp"

#include <Arduino.h>


#define SS_PIN 5
#define RST_PIN 13

// LED핀 설정 -> 기본 내장 파랑 LED인 2번 사용
#define LED_PIN 2

// #define ServerURL "http://chlrlgus.iptime.org:8000/RFID/test/"
#define ServerURL "http://192.168.0.104:8000/RFID/test/"
// 문 상태 업데이트 URL 추가
// #define DoorStatusURL "http://chlrlgus.iptime.org:8000/RFID/door_status_update/"

MFRC522 rfid(SS_PIN, RST_PIN); // Instance of the class

// // Init array that will store new NUID 
// byte nuidPICC[4];
char hexID[9];  // 서버에 값 보낼때 여기 저장
// const char* ssid = "iptimenet";
// const char* password = "a123456789";

void onWiFiConnected(String ip) {
    Serial.println("WiFi 연결됨! IP: " + ip);
    // 여기에 WiFi 연결 후 실행할 코드 작성
    // 예: MQTT 연결, 서버 통신 등
}

void onWiFiDisconnected() {
    Serial.println("WiFi 연결 끊김!");
    // 여기에 WiFi 끊김 시 실행할 코드 작성
    // 예: 데이터 저장, 알림 등
}

WiFiConfigManager wifiManager(2); // 2번핀 확인용 (2번핀은 내장 LED (아마도))

void setup() { 
  Serial.begin(115200);
  SPI.begin(); // Init SPI bus
  rfid.PCD_Init(); // Init MFRC522

  // WiFi 매니저 연결 
  wifiManager.onWiFiConnected(onWiFiConnected);
  wifiManager.onWiFiDisconnected(onWiFiDisconnected);
  
  // WiFi 매니저 시작
  bool connected = wifiManager.begin();
  // WiFi 설정 초기화 (필요시에만)
  // wifiManager.clearSettings(true);
  // WiFi 저전력 모드 실행
  wifiManager.setSleep(true);

  if(connected) {
    Serial.println("WiFi 연결 완료!");
    Serial.println("디바이스 코드: " + wifiManager.getDeviceCode());
  } else {
    Serial.println("AP 모드로 시작됨. 설정이 필요합니다.");
  }
}

void loop() {
  wifiManager.handle();
  if(wifiManager.isConnected()) {
    // WiFi 연결됨 - 정상 작업 수행
    static unsigned long lastTAG = 0;   // 태그 한번만 되게
    // static unsigned long swChattering = 0;   // 스위치 채터링
    // Serial.println(millis());
    // Serial.println(lastAction);
    // Serial.println("--------------------------------");
    if(millis() - lastTAG > 1000) { // 1초마다
      // ====================== RFID 태그 체크 =========================
      // 모듈 근처에 카드가 붙었는지 체크
      if (!rfid.PICC_IsNewCardPresent())
        return;

      // Verify if the NUID has been readed
      // 모듈 근처 카드를 제대로 읽었는지 체크
      if (!rfid.PICC_ReadCardSerial())
        return;
      
      if(!rfid.uid.size == 8) {
        Serial.println("잘못된 사이즈. 카드 정보 확인 필요");
        return;
      }

      printHex(rfid.uid.uidByte, rfid.uid.size);
      Serial.println();

      // 카드 ID 값 저장
      memset(hexID, 0, sizeof(hexID));
      for (int i = 0; i < 4; i++) {
        sprintf(&hexID[i * 2], "%02X", rfid.uid.uidByte[i]);
      }
      Serial.printf("TAG INFO : ");
      Serial.println(hexID);

      HTTPClient http;
      http.begin(ServerURL);
      http.addHeader("Content-Type", "application/json");

      // 카드 정보와 디바이스 정보 같이 보냄
      String jsonPayload = "{\"rfid_code\": \"" + String(hexID) + "\", \"device_code\": \"" + wifiManager.getDeviceCode() + "\"}";
      // POST 요청 전송
      int httpResponseCode = http.POST(jsonPayload);
      String response = http.getString();

      Serial.print("HTTP Response code: ");
      Serial.println(httpResponseCode);
      Serial.println("Server Response: " + response);

      http.end();

      // Halt PICC
      rfid.PICC_HaltA();

      // Stop encryption on PCD
      rfid.PCD_StopCrypto1();

      lastTAG = millis();
    }
    // 너무 자주 실행되지 않게끔
    delay(500);
  } else if(wifiManager.isInConfigMode()) {
    // 설정 모드 - 사용자가 WiFi 설정 중
    static unsigned long lastConfigMsg = 0;
    if(millis() - lastConfigMsg > 10000) { // 10초마다
      Serial.println("설정 모드 - WiFi 설정을 기다리는 중...");
      Serial.println("디바이스 코드: " + wifiManager.getDeviceCode());
      lastConfigMsg = millis();
    }
  }
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
}
/**
 * Helper routine to dump a byte array as hex values to Serial. 
 */
void printHex(byte *buffer, byte bufferSize) {
  for (byte i = 0; i < bufferSize; i++) {
    Serial.print(buffer[i] < 0x10 ? "0" : "");
    Serial.print(buffer[i], HEX);
  }
}

// void printHex(byte *buffer, byte bufferSize) {
//   for (byte i = 0; i < bufferSize; i++) {
//     Serial.print(i);
//     Serial.print("번째 uidByte : ");
//     Serial.print(buffer[i], HEX);
//     Serial.println();
//   }
// }