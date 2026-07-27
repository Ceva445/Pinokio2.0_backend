/*
  ESP32 RFID → FastAPI (Pinokio 2.0)
  POST без очікування response (короткий таймаут)
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <Adafruit_PN532.h>
#include <SPI.h>
#include <SD.h>

// ===== WiFi =====
const char* WIFI_SSID = "Pinokio2";
const char* WIFI_PASS = "13243546";
const char* DEVICE_ID = "E-2";

// ===== Server =====
const char* API_URL = "https://pinokio2-0.onrender.com/api/data/";

// ===== OTA =====
// Ця версія має ЗБІГАТИСЯ з тим, що адмін вписав при заливці прошивки.
// Піднімай її при кожній новій прошивці перед Export Compiled Binary.
#define FIRMWARE_VERSION "1.0.0"
// Ендпоінт віддачі .bin (той самий хост, що й API). За замовчуванням будуємо
// його з API_URL, замінивши "/api/data/" на "/api/firmware/download".
const char* OTA_DOWNLOAD_PATH = "/api/firmware/download";

// Періодична перевірка оновлень. checkForOTA() ходить на /api/firmware/download
// з хедером x-ESP32-version — сервер віддає 304 (актуально) або .bin (нова версія).
unsigned long lastOtaCheck = 0;
const unsigned long OTA_CHECK_INTERVAL = 30UL * 60UL * 1000UL; // 30 хв

// ===== SD =====
#define SD_CS 5

String sd_WIFI_SSID;
String sd_WIFI_PASS;
String sd_DEVICE_ID;
String sd_API_URL;
bool configLoaded = false;

// ===== RFID (PN532) =====
#define SDA_PIN 21
#define SCL_PIN 22
Adafruit_PN532 nfc(SDA_PIN, SCL_PIN);

// ===== Buzzer =====
#define BUZZER_PIN 25
#define BUZZER_INVERTED true

// Анти-дубль
String lastUID = "";
unsigned long lastSend = 0;
const unsigned long SEND_DELAY = 1000;

// WiFi reconnect
unsigned long lastWifiCheck = 0;
const unsigned long WIFI_RECONNECT_INTERVAL = 5000;


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

    else if (line.startsWith("API_URL="))
      sd_API_URL = line.substring(8);
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

  // Два коротких звукових сигнали, що пристрій готовий до роботи
  beep(100);
  delay(150);
  beep(100);

  // Перевірка OTA при старті
  checkForOTA();
}

// ===== Loop =====
void loop() {
  checkWiFi();

  // OTA: періодична перевірка оновлень (сервер сам вирішує 304 / .bin)
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
  beep(300);

  sendToServer(uidStr);
}

// ===== Побудувати базовий URL сервера (без "/api/data/...") =====
String serverOrigin() {
  String urlBase = (configLoaded && sd_API_URL.length()) ? sd_API_URL : String(API_URL);
  // urlBase виглядає як "https://host/api/data/" → відрізаємо "/api/data/"
  int idx = urlBase.indexOf("/api/");
  if (idx > 0) return urlBase.substring(0, idx);
  return urlBase;
}

// ===== HTTP POST (short timeout) =====
void sendToServer(const String& uid) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.setTimeout(200);

  String urlBase = (configLoaded && sd_API_URL.length()) ? sd_API_URL : String(API_URL);
  String devId   = (configLoaded && sd_DEVICE_ID.length()) ? sd_DEVICE_ID : String(DEVICE_ID);

  String fullUrl = urlBase + devId;

  http.begin(fullUrl);
  http.addHeader("Content-Type", "application/json");

  String body = "{\"rfid\":\"" + uid + "\"}";
  http.POST(body);

  http.end();
}

// ===== OTA: завантажити й прошити активну версію з сервера =====
void checkForOTA() {
  if (WiFi.status() != WL_CONNECTED) return;

  lastOtaCheck = millis();

  String url = serverOrigin() + String(OTA_DOWNLOAD_PATH);
  Serial.println("OTA: перевірка " + url + " (поточна " FIRMWARE_VERSION ")");

  // Обираємо клієнт залежно від протоколу
  t_httpUpdate_return ret;
  if (url.startsWith("https")) {
    WiFiClientSecure client;
    client.setInsecure();               // без перевірки CA (простіше)
    httpUpdate.rebootOnUpdate(true);
    // 3-й аргумент → піде хедером x-ESP32-version; сервер поверне 304, якщо збіг
    ret = httpUpdate.update(client, url, FIRMWARE_VERSION);
  } else {
    WiFiClient client;
    httpUpdate.rebootOnUpdate(true);
    ret = httpUpdate.update(client, url, FIRMWARE_VERSION);
  }

  switch (ret) {
    case HTTP_UPDATE_NO_UPDATES:        // 304 — вже актуальна
      Serial.println("OTA: вже актуальна");
      break;
    case HTTP_UPDATE_FAILED:
      Serial.printf("OTA FAILED (%d): %s\n",
        httpUpdate.getLastError(),
        httpUpdate.getLastErrorString().c_str());
      break;
    case HTTP_UPDATE_OK:
      Serial.println("OTA OK");         // зазвичай сюди не дійде — буде reboot
      break;
  }
}