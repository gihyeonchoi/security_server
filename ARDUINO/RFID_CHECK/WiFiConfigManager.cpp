#include "WiFiConfigManager.h"

// HTML 템플릿
const char* custom_html = R"(
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>춘천 폴리텍 보안 모듈 연결 설정 페이지</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; 
            display: flex; 
            align-items: center; 
            justify-content: center;
            padding: 20px;
        }
        .container { 
            max-width: 400px; 
            width: 100%;
            background: white; 
            padding: 40px 30px; 
            border-radius: 20px; 
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            backdrop-filter: blur(10px);
        }
        .logo { text-align: center; margin-bottom: 30px; }
        .logo h1 { 
            color: #667eea; 
            font-size: 28px; 
            font-weight: 700;
            margin-bottom: 5px;
        }
        .device-info { 
            text-align: center; 
            background: #f8f9fa; 
            padding: 15px; 
            border-radius: 10px; 
            margin-bottom: 25px;
            font-size: 14px;
            color: #6c757d;
        }
        .form-group { margin-bottom: 20px; }
        label { 
            display: block; 
            margin-bottom: 8px; 
            font-weight: 600; 
            color: #495057;
            font-size: 14px;
        }
        select, input { 
            width: 100%; 
            padding: 12px 15px; 
            border: 2px solid #e9ecef; 
            border-radius: 10px; 
            font-size: 16px;
            transition: all 0.3s ease;
            background-color: #fff;
        }
        select:focus, input:focus { 
            outline: none; 
            border-color: #667eea; 
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        .btn { 
            width: 100%; 
            padding: 15px; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; 
            border: none; 
            border-radius: 10px; 
            font-size: 16px; 
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s ease;
            margin-top: 10px;
        }
        .btn:hover { transform: translateY(-2px); }
        .btn:active { transform: translateY(0); }
        .info { 
            background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
            padding: 15px; 
            border-radius: 10px; 
            margin-bottom: 25px;
            border-left: 4px solid #2196f3;
            font-size: 14px;
            color: #1565c0;
        }
        .spinner { 
            display: none; 
            width: 20px; 
            height: 20px; 
            border: 2px solid #ffffff; 
            border-top: 2px solid transparent; 
            border-radius: 50%; 
            animation: spin 1s linear infinite; 
            margin-left: 10px;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>춘천 폴리텍 보안 모듈 연결 설정 페이지</h1>
        </div>
        <div class="device-info">
            <strong>디바이스 ID:</strong> DEVICE_MAC<br>
            <strong>디바이스 코드:</strong> AP_NAME<br>
        </div>
        <div class="info">
            연결할 네트워크를 선택하고 비밀번호를 입력하세요.
            ※ 디바이스 코드는 서버에 등록해야 하기 때문에 기억해두셔야 합니다 ※
        </div>
        <form id="wifiForm" method="POST" action="/connect">
            <div class="form-group">
                <label for="ssid">연결 가능한 WiFi 목록</label>
                <select name="ssid" id="ssid" required>
                    <option value="">연결할 WiFi를 선택하세요</option>
                    WIFI_NETWORKS
                </select>
            </div>
            <div class="form-group">
                <label for="password">비밀번호</label>
                <input type="password" name="password" id="password" placeholder="WiFi 비밀번호를 입력하세요">
            </div>
            <button type="submit" class="btn">
                연결하기 <span class="spinner" id="spinner"></span>
            </button>
        </form>
    </div>
    <script>
        document.getElementById('wifiForm').onsubmit = function() {
            document.getElementById('spinner').style.display = 'inline-block';
            this.querySelector('button').disabled = true;
        };
        setTimeout(() => location.reload(), 30000);
    </script>
</body>
</html>
)";

WiFiConfigManager::WiFiConfigManager(int led_pin) : server(80), ledPin(led_pin), isConfigMode(false) {
    pinMode(ledPin, OUTPUT);
    digitalWrite(ledPin, LOW);
}

bool WiFiConfigManager::begin() {
    preferences.begin("wifi-config", false);
    
    // 저장된 WiFi 정보로 연결 시도
    String savedSSID = preferences.getString("ssid", "");
    String savedPassword = preferences.getString("password", "");
    
    if(savedSSID.length() > 0) {
        Serial.println("저장된 WiFi로 연결 시도: " + savedSSID);
        WiFi.begin(savedSSID.c_str(), savedPassword.c_str());
        
        int attempts = 0;
        while(WiFi.status() != WL_CONNECTED && attempts < 20) {
            delay(500);
            Serial.print(".");
            attempts++;
        }
        
        if(WiFi.status() == WL_CONNECTED) {
            Serial.println("\nWiFi 연결 성공!");
            Serial.print("IP: ");
            Serial.println(WiFi.localIP());
            digitalWrite(ledPin, HIGH);
            apName = preferences.getString("ap_name", "");
            
            if(_onConnectedCallback) {
                _onConnectedCallback(WiFi.localIP().toString());
            }
            return true;
        }
    }
    
    // WiFi 연결 실패 시 AP 모드로 전환
    startConfigPortal();
    return false;
}

void WiFiConfigManager::handle() {
    // AP 모드일 때만 DNS와 웹 서버 처리
    if(WiFi.getMode() == WIFI_AP || WiFi.getMode() == WIFI_AP_STA) {
        isConfigMode = true;
        dnsServer.processNextRequest();
        server.handleClient();
        
        // LED 깜빡임으로 설정 모드 표시
        static unsigned long lastBlink = 0;
        if(millis() - lastBlink > 1000) {
            digitalWrite(ledPin, !digitalRead(ledPin));
            lastBlink = millis();
        }
        return;
    }
    
    // Station 모드에서만 WiFi 연결 상태 확인
    if(WiFi.getMode() == WIFI_STA) {
        isConfigMode = false;
        static unsigned long lastCheck = 0;
        
        // 5초마다 체크
        if(millis() - lastCheck > 5000) {
            if(WiFi.status() != WL_CONNECTED) {
                Serial.println("WiFi 연결 끊김 - 재연결 시도");
                digitalWrite(ledPin, LOW);
                
                if(_onDisconnectedCallback) {
                    _onDisconnectedCallback();
                }
                
                WiFi.reconnect();
                unsigned long startTime = millis();
                while(WiFi.status() != WL_CONNECTED && millis() - startTime < 30000) {
                    delay(500);
                    Serial.print(".");
                }
                
                if(WiFi.status() == WL_CONNECTED) {
                    Serial.println("\n재연결 성공!");
                    digitalWrite(ledPin, HIGH);
                    
                    if(_onConnectedCallback) {
                        _onConnectedCallback(WiFi.localIP().toString());
                    }
                } else {
                    Serial.println("\n재연결 실패 - AP 모드로 전환");
                    startConfigPortal();
                }
            }
            lastCheck = millis();
        }
    }
}

void WiFiConfigManager::clearSettings(bool resetApName) {
  preferences.remove("ssid");
  preferences.remove("password");
  if (resetApName)
    preferences.remove("ap_name");
  Serial.println("WiFi 설정이 초기화되었습니다.");
  ESP.restart();
}

String WiFiConfigManager::randomApNAME(size_t length) {
    const char charset[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    String result = "";
    for (size_t i = 0; i < length; i++) {
        result += charset[random(0, sizeof(charset) - 1)];
    }
    return result;
}

void WiFiConfigManager::startConfigPortal() {
    Serial.println("AP 모드 시작...");
    
    // 저장된 AP 이름 확인
    apName = preferences.getString("ap_name", "");
    
    if (apName == "") {
        apName = randomApNAME(8);
        preferences.putString("ap_name", apName);
        Serial.println("새 랜덤 디바이스 코드 생성: " + apName);
    } else {
        Serial.println("저장된 디바이스 코드 사용: " + apName);
    }
    
    String apName_show = "춘천_폴리텍-" + apName;
    Serial.println("AP 이름 : " + apName_show);
    WiFi.softAP(apName_show.c_str(), "");
    
    dnsServer.start(53, "*", WiFi.softAPIP());
    
    server.on("/", [this]() { handleRoot(); });
    server.on("/connect", HTTP_POST, [this]() { handleConnect(); });
    server.onNotFound([this]() { handleRoot(); });
    
    server.begin();
    Serial.println("설정 서버 시작됨");
    Serial.println("AP: " + apName_show);
    Serial.println("주소: http://192.168.4.1");
}

void WiFiConfigManager::handleRoot() {
    String html = custom_html;
    
    // WiFi 스캔 전 상태 확인
    if(WiFi.getMode() != WIFI_AP) {
        WiFi.mode(WIFI_AP);
        delay(500);
    }
    
    String networks = "";
    int n = WiFi.scanNetworks();
    
    if(n == 0) {
        // 스캔 실패 시 재시도
        delay(1000);
        n = WiFi.scanNetworks();
    }
    
    for(int i = 0; i < n; i++) {
        networks += "<option value=\"" + WiFi.SSID(i) + "\">";
        networks += WiFi.SSID(i) + " (" + String(WiFi.RSSI(i)) + "dBm)";
        networks += "</option>";
    }
    
    if(networks == "") {
        networks = "<option value=\"\">스캔된 네트워크가 없습니다</option>";
    }
    
    String mac = WiFi.macAddress();
    html.replace("DEVICE_MAC", mac);
    html.replace("WIFI_NETWORKS", networks);
    html.replace("AP_NAME", apName);
    
    server.send(200, "text/html", html);
}

void WiFiConfigManager::handleConnect() {
    String ssid = server.arg("ssid");
    String password = server.arg("password");
    
    Serial.println("연결 시도: " + ssid);
    
    // 기존 연결 정리
    WiFi.disconnect(true);
    delay(100);
    
    // AP + STA 모드로 변경
    WiFi.mode(WIFI_AP_STA);
    WiFi.begin(ssid.c_str(), password.c_str());
    
    unsigned long startTime = millis();
    bool connected = false;
    
    while(millis() - startTime < 10000) {
        if(WiFi.status() == WL_CONNECTED) {
            connected = true;
            break;
        }
        delay(500);
        Serial.print(".");
    }
    
    server.sendHeader("Content-Type", "text/html; charset=UTF-8");
    
    if(connected) {
        // 연결 성공 코드 (기존과 동일)
        preferences.putString("ssid", ssid);
        preferences.putString("password", password);
        
        Serial.println("\nWiFi 연결 성공!");
        Serial.print("IP: ");
        Serial.println(WiFi.localIP());
        
        server.send(200, "text/html", 
            "<html><head><meta charset='UTF-8'></head>"
            "<body style='text-align:center;padding:50px;font-family:Arial;background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);color:white;'>"
            "<div style='background:rgba(255,255,255,0.1);padding:40px;border-radius:20px;backdrop-filter:blur(10px);'>"
            "<h2 style='color:#4CAF50;'>✅ 연결 성공</h2>"
            "<p>WiFi에 성공적으로 연결되었습니다.</p>"
            "<p>IP 주소: " + WiFi.localIP().toString() + "</p>"
            "<p>3초 후 디바이스가 Station 모드로 전환됩니다.</p>"
            "</div></body></html>"
        );
        
        delay(3000);
        WiFi.mode(WIFI_STA);
        digitalWrite(ledPin, LOW);
        
        if(_onConnectedCallback) {
            _onConnectedCallback(WiFi.localIP().toString());
        }
    } else {
        // 연결 실패 - 중요: WiFi 상태 정리
        Serial.println("\n연결 실패");
        
        WiFi.disconnect(true);  // 연결 시도 중단
        delay(500);             // 안정화 대기
        WiFi.mode(WIFI_AP);     // AP 모드로 복원
        delay(500);             // 모드 변경 대기
        
        // AP 재시작 (기존 설정 유지)
        String apName_show = "춘천_폴리텍-" + apName;
        WiFi.softAP(apName_show.c_str(), "");
        
        server.send(200, "text/html", 
            "<html><head><meta charset='UTF-8'></head>"
            "<body style='text-align:center;padding:50px;font-family:Arial;background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);color:white;'>"
            "<div style='background:rgba(255,255,255,0.1);padding:40px;border-radius:20px;backdrop-filter:blur(10px);'>"
            "<h2 style='color:#f44336;'>❌ 연결 실패</h2>"
            "<p>WiFi 연결에 실패했습니다.</p>"
            "<p>비밀번호를 확인하고 다시 시도해주세요.</p>"
            "<a href='/' style='color:##4C4C4C;text-decoration:none;background:rgba(255,255,255,0.2);padding:10px 20px;border-radius:5px;display:inline-block;margin-top:20px;'>다시 시도</a>"
            "</div></body></html>"
        );
    }
}

bool WiFiConfigManager::isConnected() {
    return WiFi.status() == WL_CONNECTED;
}

bool WiFiConfigManager::isInConfigMode() {
    return isConfigMode;
}

String WiFiConfigManager::getLocalIP() {
    return WiFi.localIP().toString();
}

String WiFiConfigManager::getDeviceCode() {
    return apName;
}

void WiFiConfigManager::onWiFiConnected(WiFiConnectedCallback callback) {
    _onConnectedCallback = callback;
}

void WiFiConfigManager::onWiFiDisconnected(WiFiDisconnectedCallback callback) {
    _onDisconnectedCallback = callback;
}

void WiFiConfigManager::setSleep(bool enabled) {
    if (enabled){
        WiFi.setSleep(true);
        Serial.println("WIFI SLEEP MODE : ON");
    } else { 
        WiFi.setSleep(false);
        Serial.println("WIFI SLEEP MODE : OFF");
    }
}