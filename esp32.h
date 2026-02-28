/*
  ESP32 RFID → FastAPI (Pinokio 2.0)
  POST без очікування response (короткий таймаут)
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_PN532.h>
#include <SPI.h>
#include <SD.h>

// ===== WiFi =====
const char* WIFI_SSID = "AP_PiatekCeva";
const char* WIFI_PASS = "Orange3546";
const char* DEVICE_ID = "E-2";

// ===== Server =====
const char* API_URL = "https://pinokio2-0.onrender.com/api/data/";

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
  digitalWrite(BUZZER_PIN, HIGH);
  delay(duration);
  digitalWrite(BUZZER_PIN, LOW);
}

// ===== Setup =====
void setup() {
  Serial.begin(115200);

  loadConfigFromSD();   // ← ДОДАНО

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

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
}

// ===== Loop =====
void loop() {
  checkWiFi();

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