#pragma once
#include <Arduino.h>

// === Configuration ===
#define WIFI_SSID "frybin"
#define WIFI_PASS "y2nxckwy"

#define GMT_OFFSET_SEC 3600        // Adjust for your timezone
#define DAYLIGHT_OFFSET_SEC 3600   // Adjust if DST applies

// === Wi-Fi ===
bool initWiFi();                          // Init Wi-Fi hardware
bool connectToWiFi(uint32_t timeoutMs);   // Connect with timeout
bool isWiFiConnected();
bool recoverWiFi(uint32_t timeoutMs);

// === NTP Time ===
bool syncTime(uint32_t timeoutMs);
bool isTimeSynced();
time_t getTimestamp();
String getFormattedTime();
void disconnectWiFi();
bool isTimeSaneNow();


// // === MQTT (to implement later) ===
// bool connectToMQTT(uint32_t timeoutMs);
// bool isMQTTConnected();
// bool publishMQTT(const char* topic, const char* payload);
// bool subscribeMQTT(const char* topic);
// bool recoverMQTT(uint32_t timeoutMs);

// // === Web services (optional debug/streaming) ===
// void startNetworkServices();  // HTTP + WS
// void sendWAVBuffer(const uint8_t* data, size_t len);
// void sendFFTFrame(const float* freqs, const float* mags, size_t count);
// void updateWebSocket();
