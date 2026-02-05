/*
  ESP32 RFID → FastAPI (Pinokio 2.0)
  POST без очікування response (короткий таймаут)
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_PN532.h>

// ===== WiFi =====
const char* WIFI_SSID = "AP_PiatekCeva";
const char* WIFI_PASS = "Orange3546";
const char* DEVICE_ID = "E-2";

// ===== Server =====
const char* API_URL = "https://pinokio2-0.onrender.com/api/data/";

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

// ===== WiFi check =====
void checkWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  unsigned long now = millis();
  if (now - lastWifiCheck < WIFI_RECONNECT_INTERVAL) return;

  lastWifiCheck = now;
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
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

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
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

  String fullUrl = String(API_URL) + DEVICE_ID;
  http.begin(fullUrl);
  http.addHeader("Content-Type", "application/json");

  String body = "{\"rfid\":\"" + uid + "\"}";
  http.POST(body);

  http.end();
}