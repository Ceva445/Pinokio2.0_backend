/*
  ESP32 RFID → FastAPI (Pinokio 2.0)
  POST без очікування response (короткий таймаут)
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <MFRC522v2.h>
#include <MFRC522DriverSPI.h>
#include <MFRC522DriverPinSimple.h>

// ===== WiFi =====
const char* WIFI_SSID = "Malydomek1";
const char* WIFI_PASS = "Malydomek1";
const char* DEVICE_ID = "device-id";

// ===== Server =====
const char* API_URL = "https://pinokio2-0.onrender.com/api/data/";

// ===== RFID =====
MFRC522DriverPinSimple ss_pin(5);
MFRC522DriverSPI driver{ ss_pin };
MFRC522 rfid{ driver };

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

  // RFID
  rfid.PCD_Init();
  Serial.println("RFID ready");
}

// ===== Loop =====
void loop() {
  checkWiFi();

  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  // UID → string
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
    if (i < rfid.uid.size - 1) uid += ":";
  }
  uid.toUpperCase();

  unsigned long now = millis();
  if (uid == lastUID && now - lastSend < SEND_DELAY) {
    rfid.PICC_HaltA();
    return;
  }

  lastUID = uid;
  lastSend = now;

  Serial.println("RFID: " + uid);
  beep(300);

  sendToServer(uid);

  rfid.PICC_HaltA();
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