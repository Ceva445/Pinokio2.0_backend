/*
  ESP32 RFID → FastAPI (Pinokio 2.0)
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
const char* API_URL = "https://pinokio2-0-backend.onrender.com/api/data/";

// ===== RFID =====
MFRC522DriverPinSimple ss_pin(5);
MFRC522DriverSPI driver{ ss_pin };
MFRC522 rfid{ driver };

// Анти-дубль
String lastUID = "";
unsigned long lastSend = 0;
const unsigned long SEND_DELAY = 1000; // 1 сек

void setup() {
  Serial.begin(115200);

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

void loop() {
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

  sendToServer(uid);

  rfid.PICC_HaltA();
}

// ===== HTTP POST =====
void sendToServer(const String& uid) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String fullUrl = String(API_URL) + DEVICE_ID;

  http.begin(fullUrl);
  http.addHeader("Content-Type", "application/json");

  String body = "{\"rfid\":\"" + uid + "\"}";
  int code = http.POST(body);

  Serial.print("POST ");
  Serial.print(code);
  Serial.print(" → ");
  Serial.println(body);

  http.end();
}