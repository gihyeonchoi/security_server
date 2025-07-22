#ifndef WIFI_CONFIG_MANAGER_H
#define WIFI_CONFIG_MANAGER_H

#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>

class WiFiConfigManager {
  private:
      WebServer server;
      DNSServer dnsServer;
      Preferences preferences;
      String apName;
      int ledPin;
      bool isConfigMode;
      
      // 내부 함수들
      String randomApNAME(size_t length);
      void startConfigPortal();
      void handleRoot();
      void handleConnect();
      
  public:
      // 생성자
      WiFiConfigManager(int led_pin = 2);
      
      // 초기화 및 WiFi 연결
      bool begin();
      
      // 메인 루프에서 호출할 함수
      void handle();
      
      // WiFi 설정 초기화
      void clearSettings(bool resetApName);
      
      // 상태 확인 함수들
      bool isConnected();
      bool isInConfigMode();
      String getLocalIP();
      String getDeviceCode();
      
      // 콜백 함수 타입 정의
      typedef void (*WiFiConnectedCallback)(String ip);
      typedef void (*WiFiDisconnectedCallback)();

      // 슬립모드 설정
      void setSleep (bool enabled);
      
      // 콜백 설정
      void onWiFiConnected(WiFiConnectedCallback callback);
      void onWiFiDisconnected(WiFiDisconnectedCallback callback);
      
  private:
      WiFiConnectedCallback _onConnectedCallback = nullptr;
      WiFiDisconnectedCallback _onDisconnectedCallback = nullptr;
};

#endif