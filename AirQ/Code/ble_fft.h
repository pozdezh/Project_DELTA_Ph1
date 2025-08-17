#pragma once
#include <Arduino.h>

// === BLE Initialization ===
// Call once at boot
void initBLE();

// === Start advertising manually ===
// Normally triggered automatically in sendPeakOverBLE() if not connected
void startBLEAdvertising();

// === Send FFT peak data over BLE ===
// If not connected, will start advertising and wait for connection
void sendPeakOverBLE(float freq, float magnitude);

// === Check BLE connection status ===
bool isBLEConnected();
