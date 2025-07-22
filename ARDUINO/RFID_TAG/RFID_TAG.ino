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

// 도어센서 핀 설정
#define DOOR_SENSOR_PIN 27

// 안쪽 문열림 핀 설정
#define DOOR_OPEN_SWITCH 26

// 솔레노이드 락 핀 설정
#define SOLENOID_LOCK 25

// LED핀 설정 -> 기본 내장 파랑 LED인 2번 사용
#define LED_PIN 2

// #define ServerURL "http://chlrlgus.iptime.org:8000/RFID/test/"
#define ServerURL "http://192.168.0.104:8000/RFID/card_use/"
// 문 상태 업데이트 URL 추가
//#define DoorStatusURL "http://chlrlgus.iptime.org:8000/RFID/door_status_update/"
#define DoorStatusURL "http://192.168.0.104:8000/RFID/door_status_update/"

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

  // 도어센서 pin 연결
  pinMode(DOOR_SENSOR_PIN, INPUT_PULLUP);

  // 문열림 스위치 pin 연결
  pinMode(DOOR_OPEN_SWITCH, INPUT_PULLUP);

  // 솔레노이드 잠금장치 pin 연결
  pinMode(SOLENOID_LOCK, OUTPUT);

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

// 없으면 처음 실행마다 계속 초기화됨
bool isFirstStart = true;

// 도어 센서
int SENSOR_STATE = 0;
int LAST_SENSOR_STATE = 0;  // 이전 센서 상태 저장

// 문 열림 스위치
int SWITCH_STATE = 0; // sw 입력값 read
int buttonState;
int lastButtonState = LOW;
unsigned long buttonPressTime = 0;  // 버튼 누른시간 체크
unsigned long lastDebounceTime = 0;
int debounceDelay=100;
int debounceDelay_For_Init_Setting = 5000;  // 세팅 초기화

// 문 열림/닫힘 확인용
bool isDoorOpen = false;
bool autoLockDone = false;  // 자동 잠금 동작 완료 여부
bool lastDoorOpenState = false;  // 이전 문 열림 상태 저장

// 솔레노이드 잠금장치 자동 잠금
int autoLockTime = 2000;
unsigned long doorOpenTime = 0;

// 마지막 문 상태 업데이트 시간 (너무 자주 전송하지 않게 제한)
unsigned long lastDoorStatusUpdate = 0;
const unsigned long DOOR_STATUS_UPDATE_INTERVAL = 1000; // 1초마다 최대 1번

void auto_door_lock() {
  if(!isDoorOpen && !autoLockDone && ((millis() - doorOpenTime) > autoLockTime)){
    digitalWrite(SOLENOID_LOCK, LOW);
    Serial.println("자동으로 문닫힘");
    autoLockDone = true; // 한 번만 실행되게 플래그 ON
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

    // ====================== 자동 문잠김 ======================
    if(!isDoorOpen && !autoLockDone && ((millis() - doorOpenTime) > autoLockTime)){
      digitalWrite(SOLENOID_LOCK, LOW);
      Serial.println("자동으로 문닫힘");
      autoLockDone = true; // 한 번만 실행되게 플래그 ON
    }
    // ====================== 스위치 동작 체크 ======================
    SWITCH_STATE = digitalRead(DOOR_OPEN_SWITCH);

    if (SWITCH_STATE != lastButtonState){
      lastDebounceTime = millis();
    }
    
    if ((millis() - lastDebounceTime) > debounceDelay) {
      if (SWITCH_STATE != buttonState) {
        buttonState = SWITCH_STATE;
        if (buttonState == LOW) {
          buttonPressTime = millis();
        } else {
          unsigned long pressDuration = millis() - buttonPressTime;
          if (pressDuration >= debounceDelay_For_Init_Setting && !isFirstStart) {
            Serial.println("길게누름 : 초기화함");
            wifiManager.clearSettings(true);
          } else {
            Serial.println("짧게누름 : 문열림");
            digitalWrite(SOLENOID_LOCK, HIGH);
          }
        }
      }
    }
    lastButtonState = SWITCH_STATE;

    // ====================== 도어센서 체크 =========================
    SENSOR_STATE = digitalRead(DOOR_SENSOR_PIN);
    // Serial.print("센서 상태 : ");
    // Serial.println(SENSOR_STATE);
    
    // 센서 상태 변경 감지
    if(SENSOR_STATE != LAST_SENSOR_STATE) {
      Serial.println("센서 상태 변경 감지!");
      LAST_SENSOR_STATE = SENSOR_STATE;
    }
    
    if(SENSOR_STATE == HIGH) {
      isDoorOpen = true;
      doorOpenTime = millis();
      autoLockDone = false; // 문이 다시 열리면 자동 잠금 플래그 리셋
    } else {
      isDoorOpen = false;
    }

    // ====================== 문 상태 서버 전송 ======================
    // 문 상태가 변경되었고, 마지막 업데이트로부터 충분한 시간이 지났을 때만 전송
    if(isDoorOpen != lastDoorOpenState && 
       (millis() - lastDoorStatusUpdate) > DOOR_STATUS_UPDATE_INTERVAL) {
      
      Serial.println("문 상태 변경 감지 - 서버에 전송");
      sendDoorStatusToServer(isDoorOpen);
      lastDoorOpenState = isDoorOpen;
      lastDoorStatusUpdate = millis();
    }

    // ====================== 중간 내용 =============================
    
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

      // json response 를 저장할곳
      StaticJsonDocument<512> doc;
      DeserializationError error = deserializeJson(doc, response);
      if (error) {
        Serial.print("JSON 파싱 오류: ");
        Serial.println(error.f_str());
        for (int i = 0; i < 3; i++) {
          digitalWrite(LED_PIN, HIGH);
          delay(150);
          digitalWrite(LED_PIN, LOW);
          delay(150);
        }
      } else {
        const char* status = doc["status"];
        if (strcmp(status, "success") == 0) {
          Serial.println("출입 허용");
          digitalWrite(SOLENOID_LOCK, HIGH);
          digitalWrite(LED_PIN, HIGH);
          delay(2000);
          digitalWrite(LED_PIN, LOW);
        } else {
          Serial.println("출입 거부");
          for (int i = 0; i < 3; i++) {
            digitalWrite(LED_PIN, HIGH);
            delay(150);
            digitalWrite(LED_PIN, LOW);
            delay(150);
          }
        }
      }
      http.end();

      // Halt PICC
      rfid.PICC_HaltA();

      // Stop encryption on PCD
      rfid.PCD_StopCrypto1();

      lastTAG = millis();
    }
    // 너무 자주 실행되지 않게끔
    delay(500);
    isFirstStart = false;
  } else if(wifiManager.isInConfigMode()) {
    // 설정 모드 - 사용자가 WiFi 설정 중
    static unsigned long lastConfigMsg = 0;
    if(millis() - lastConfigMsg > 10000) { // 10초마다
      Serial.println("설정 모드 - WiFi 설정을 기다리는 중...");
      Serial.println("디바이스 코드: " + wifiManager.getDeviceCode());
      lastConfigMsg = millis();
      isFirstStart = true;
    }
  }
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
}

void sendDoorStatusToServer(bool doorStatus) {
  /**
   * 문 상태를 서버로 전송하는 함수
   * @param doorStatus: true=열림, false=닫힘
   */
  if(!wifiManager.isConnected()) {
    Serial.println("WiFi 연결 없음 - 문 상태 전송 실패");
    return;
  }
  
  HTTPClient http;
  http.begin(DoorStatusURL);
  http.addHeader("Content-Type", "application/json");
  Serial.print("\n" + wifiManager.getDeviceCode() + "\n");
  // JSON 데이터 생성
  String jsonPayload = "{\"device_code\": \"" + wifiManager.getDeviceCode() + 
                      "\", \"door_status\": " + (doorStatus ? "true" : "false") + "}";
  
  Serial.println("문 상태 전송 데이터: " + jsonPayload);
  
  // POST 요청 전송
  int httpResponseCode = http.POST(jsonPayload);
  String response = http.getString();
  StaticJsonDocument<512> doc;
  DeserializationError error = deserializeJson(doc, response);

  if (!error) {
    const char* status = doc["status"];
    const char* message = doc["message"];

    Serial.print("파싱된 status: ");
    Serial.println(status);

    Serial.print("파싱된 message: ");
    Serial.println(message);  // 여기서 한글로 잘 보임
  } else {
    Serial.println("문 상태 JSON 파싱 오류");
  }
  
  if(httpResponseCode == 200) {
    // JSON 응답 파싱
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, response);
    if (!error) {
      const char* status = doc["status"];
      if (strcmp(status, "success") == 0) {
        Serial.println("문 상태 서버 업데이트 성공");
        // LED로 성공 신호 (짧게 깜빡)
        digitalWrite(LED_PIN, HIGH);
        delay(100);
        digitalWrite(LED_PIN, LOW);
      } else {
        Serial.println("문 상태 서버 업데이트 실패: " + String(doc["message"].as<String>()));
      }
    } else {
      Serial.println("문 상태 응답 JSON 파싱 오류");
    }
  } else {
    Serial.println("문 상태 전송 HTTP 오류: " + String(httpResponseCode));
  }
  
  http.end();
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