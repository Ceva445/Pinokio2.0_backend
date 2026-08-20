/*
  ESP32 RFID → FastAPI (Pinokio 2.0)
  ТРАНСПОРТ: WebSocket (постійне зʼєднання) замість HTTP POST.

  Чому швидше:
    - TLS/TCP-хендшейк відбувається ОДИН раз при конекті, а не на кожен скан;
    - кожен RFID — це маленький текстовий фрейм у вже відкритому сокеті → затримка ~RTT;
    - сервер сам тримає інстанс "теплим" (немає cold start).

  Протокол:
    ESP → сервер:  {"rfid":"AA:BB:CC:DD"}
    сервер → ESP:  {"type":"ack","status":"success|error|info|warning","message":"..."}
                   → ESP пікає відповідним тоном (фідбек користувачу).

  Потрібна бібліотека: "WebSockets" by Markus Sattler (Links2004/arduinoWebSockets).
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <WiFiClientSecure.h>
#include <WebSocketsClient.h>
#include <Wire.h>
#include <Adafruit_PN532.h>
#include <SPI.h>
#include <SD.h>

// ===== WiFi =====
const char* WIFI_SSID = "Pinokio2";
const char* WIFI_PASS = "13243546";
const char* DEVICE_ID = "E-2";

// ===== Server (WebSocket) =====
// Підключення через публічний домен по wss:// (TLS). Один TLS-хендшейк на конект,
// далі кожен скан — маленький фрейм у відкритому сокеті.
//
// БЕЗПЕКА: адресу сервера НЕ хардкодимо у вихідник (він лежить у git-репо).
// Реальний домен задається у /config.txt на SD-карті:
//     SERVER_HOST=twoj-domen.example.com
//     SERVER_PORT=443
const char*   SERVER_HOST = "https://pinokio2-0.onrender.com/api/data/";    // порожньо → береться з SD config.txt (SERVER_HOST=)
const uint16_t SERVER_PORT = 443;  // wss:// за замовчуванням; SD може перекрити (SERVER_PORT=)
const bool    WS_USE_TLS   = true;  // true → beginSSL (wss://)

// ===== OTA (лишається по HTTP — не критично до затримки) =====
// Ця версія має ЗБІГАТИСЯ з тим, що адмін вписав при заливці прошивки.
#define FIRMWARE_VERSION "1.0.0"
const char* OTA_DOWNLOAD_PATH = "/api/firmware/download";

unsigned long lastOtaCheck = 0;
const unsigned long OTA_CHECK_INTERVAL = 30UL * 60UL * 1000UL; // 30 хв

// ===== SD =====
#define SD_CS 5

String sd_WIFI_SSID;
String sd_WIFI_PASS;
String sd_DEVICE_ID;
String sd_SERVER_HOST;
String sd_SERVER_PORT;
bool configLoaded = false;

// ===== RFID (PN532) =====
#define SDA_PIN 21
#define SCL_PIN 22
Adafruit_PN532 nfc(SDA_PIN, SCL_PIN);

// ===== Buzzer =====
#define BUZZER_PIN 25
#define BUZZER_INVERTED true

// ===== WebSocket =====
WebSocketsClient webSocket;
bool wsConnected = false;

// Анти-дубль
String lastUID = "";
unsigned long lastSend = 0;
const unsigned long SEND_DELAY = 1000;

// WiFi reconnect
unsigned long lastWifiCheck = 0;
const unsigned long WIFI_RECONNECT_INTERVAL = 5000;


// =======================
// CONFIG HELPERS (SD override або дефолти)
// =======================
String cfgDeviceId() {
  return (configLoaded && sd_DEVICE_ID.length()) ? sd_DEVICE_ID : String(DEVICE_ID);
}
String cfgHost() {
  return (configLoaded && sd_SERVER_HOST.length()) ? sd_SERVER_HOST : String(SERVER_HOST);
}
uint16_t cfgPort() {
  return (configLoaded && sd_SERVER_PORT.length()) ? (uint16_t) sd_SERVER_PORT.toInt() : SERVER_PORT;
}

// =======================
// LOAD CONFIG FROM SD
// =======================
void loadConfigFromSD() {
  if (!SD.begin(SD_CS)) {
    Serial.println("SD not found → defaults");
    return;
  }

  File file = SD.open("/config.txt");
  if (!file) {
    Serial.println("config.txt not found → defaults");
    return;
  }

  Serial.println("Reading config.txt");

  while (file.available()) {
    String line = file.readStringUntil('\n');
    line.trim();

    if (line.startsWith("WIFI_SSID="))
      sd_WIFI_SSID = line.substring(10);

    else if (line.startsWith("WIFI_PASS="))
      sd_WIFI_PASS = line.substring(10);

    else if (line.startsWith("DEVICE_ID="))
      sd_DEVICE_ID = line.substring(10);

    else if (line.startsWith("SERVER_HOST="))
      sd_SERVER_HOST = line.substring(12);

    else if (line.startsWith("SERVER_PORT="))
      sd_SERVER_PORT = line.substring(12);
  }

  file.close();
  configLoaded = true;

  Serial.println("Config loaded from SD");
}

// ===== WiFi check =====
void checkWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  unsigned long now = millis();
  if (now - lastWifiCheck < WIFI_RECONNECT_INTERVAL) return;

  lastWifiCheck = now;
  WiFi.disconnect();

  const char* ssid = (configLoaded && sd_WIFI_SSID.length()) ? sd_WIFI_SSID.c_str() : WIFI_SSID;
  const char* pass = (configLoaded && sd_WIFI_PASS.length()) ? sd_WIFI_PASS.c_str() : WIFI_PASS;

  WiFi.begin(ssid, pass);
}

// ===== Buzzer =====
void beep(int duration = 100) {
  digitalWrite(BUZZER_PIN, BUZZER_INVERTED ? LOW : HIGH);
  delay(duration);
  digitalWrite(BUZZER_PIN, BUZZER_INVERTED ? HIGH : LOW);
}

void beepSuccess() {   // два коротких — ОК
  beep(70);
  delay(60);
  beep(70);
}

void beepError() {     // один довгий — помилка/увага
  beep(400);
}

// ===== WebSocket event handler =====
void onWsEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      wsConnected = true;
      Serial.println("WS connected");
      beep(60); // короткий сигнал, що канал відкрито
      break;

    case WStype_DISCONNECTED:
      wsConnected = false;
      Serial.println("WS disconnected");
      break;

    case WStype_TEXT: {
      // Формуємо рядок строго по довжині (payload не завжди null-terminated)
      String msg;
      msg.reserve(length + 1);
      for (size_t i = 0; i < length; i++) msg += (char) payload[i];

      Serial.println("WS ack: " + msg);

      if (msg.indexOf("\"status\":\"success\"") >= 0)      beepSuccess();
      else if (msg.indexOf("\"status\":\"error\"") >= 0)   beepError();
      else if (msg.indexOf("\"status\":\"warning\"") >= 0) beepError();
      break;
    }

    default:
      break;
  }
}

// ===== WebSocket setup =====
void setupWebSocket() {
  String path = "/ws/device/" + cfgDeviceId();
  String host = cfgHost();
  uint16_t port = cfgPort();

  if (host.length() == 0) {
    Serial.println("WS: SERVER_HOST не заданий — додай 'SERVER_HOST=...' у /config.txt на SD");
    return; // без хоста не підключаємось
  }

  Serial.printf("WS target: %s://%s:%u%s\n",
                WS_USE_TLS ? "wss" : "ws", host.c_str(), port, path.c_str());

  if (WS_USE_TLS) {
    webSocket.beginSSL(host.c_str(), port, path.c_str());
  } else {
    webSocket.begin(host.c_str(), port, path.c_str());
  }

  webSocket.onEvent(onWsEvent);
  webSocket.setReconnectInterval(3000);        // автопере-підключення
  webSocket.enableHeartbeat(15000, 3000, 2);   // ping кожні 15с, timeout 3с, 2 промахи → reconnect
}

// ===== Setup =====
void setup() {
  Serial.begin(115200);

  loadConfigFromSD();

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, BUZZER_INVERTED ? HIGH : LOW);

  // WiFi
  const char* ssid = (configLoaded && sd_WIFI_SSID.length()) ? sd_WIFI_SSID.c_str() : WIFI_SSID;
  const char* pass = (configLoaded && sd_WIFI_PASS.length()) ? sd_WIFI_PASS.c_str() : WIFI_PASS;

  WiFi.begin(ssid, pass);
  WiFi.setSleep(false); // вимкнути modem sleep → менша затримка радіо

  Serial.print("WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");

  // RFID (PN532)
  Wire.begin(SDA_PIN, SCL_PIN);
  nfc.begin();

  uint32_t version = nfc.getFirmwareVersion();
  if (!version) {
    Serial.println("PN532 not found!");
    while (1);
  }

  nfc.SAMConfig();
  Serial.println("PN532 ready");

  // Перевірка OTA при старті (по HTTP)
  checkForOTA();

  // Відкриваємо постійний WebSocket
  setupWebSocket();

  // Два коротких сигнали — пристрій готовий
  beep(100);
  delay(150);
  beep(100);
}

// ===== Надіслати RFID через WebSocket =====
void sendRFID(const String& uid) {
  if (!wsConnected) {
    Serial.println("WS not connected → skip send");
    return;
  }
  String body = "{\"rfid\":\"" + uid + "\"}";
  webSocket.sendTXT(body);
}

// ===== Loop =====
void loop() {
  checkWiFi();
  webSocket.loop(); // ОБОВʼЯЗКОВО: обслуговує сокет, heartbeat, reconnect

  // OTA: періодична перевірка оновлень
  if (millis() - lastOtaCheck > OTA_CHECK_INTERVAL) {
    checkForOTA();
  }

  uint8_t uid[] = {0, 0, 0, 0, 0, 0, 0};
  uint8_t uidLength;

  if (!nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 100)) {
    return;
  }

  // UID → string
  String uidStr = "";
  for (byte i = 0; i < uidLength; i++) {
    if (uid[i] < 0x10) uidStr += "0";
    uidStr += String(uid[i], HEX);
    if (i < uidLength - 1) uidStr += ":";
  }
  uidStr.toUpperCase();

  unsigned long now = millis();
  if (uidStr == lastUID && now - lastSend < SEND_DELAY) {
    return;
  }

  lastUID = uidStr;
  lastSend = now;

  Serial.println("RFID: " + uidStr);

  // СПЕРШУ відправляємо (мінімальна затримка), фідбек прийде в ack.
  sendRFID(uidStr);
  beep(60); // короткий "клац" — картку прочитано
}

// ===== Побудувати базовий origin сервера для OTA =====
// Схема узгоджена з WS_USE_TLS: wss → https, ws → http.
String serverOrigin() {
  String scheme = WS_USE_TLS ? "https" : "http";
  return scheme + "://" + cfgHost() + ":" + String(cfgPort());
}

// ===== OTA: завантажити й прошити активну версію з сервера =====
void checkForOTA() {
  if (WiFi.status() != WL_CONNECTED) return;

  lastOtaCheck = millis();

  String url = serverOrigin() + String(OTA_DOWNLOAD_PATH);
  Serial.println("OTA: перевірка " + url + " (поточна " FIRMWARE_VERSION ")");

  t_httpUpdate_return ret;
  if (url.startsWith("https")) {
    WiFiClientSecure client;
    client.setInsecure();
    httpUpdate.rebootOnUpdate(true);
    ret = httpUpdate.update(client, url, FIRMWARE_VERSION);
  } else {
    WiFiClient client;
    httpUpdate.rebootOnUpdate(true);
    ret = httpUpdate.update(client, url, FIRMWARE_VERSION);
  }

  switch (ret) {
    case HTTP_UPDATE_NO_UPDATES:
      Serial.println("OTA: вже актуальна");
      break;
    case HTTP_UPDATE_FAILED:
      Serial.printf("OTA FAILED (%d): %s\n",
        httpUpdate.getLastError(),
        httpUpdate.getLastErrorString().c_str());
      break;
    case HTTP_UPDATE_OK:
      Serial.println("OTA OK");
      break;
  }
}
