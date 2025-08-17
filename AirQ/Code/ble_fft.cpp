#include "ble_fft.h"
#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <ctime>
#include "freertos/FreeRTOS.h"
#include "freertos/timers.h"

// === UUIDs for Nordic UART-compatible service ===
#define BLE_SERVICE_UUID        "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define BLE_CHARACTERISTIC_UUID "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

static BLECharacteristic* pCharacteristic = nullptr;
static BLEServer* pServer = nullptr;
static bool bleConnected = false;
static bool bleAdvertising = false;

static TimerHandle_t bleStopTimer = nullptr;
static constexpr uint32_t BLE_ADV_DURATION_MS = 10000; // advertise for 10s after trigger

static constexpr const char* BLE_DEVICE_NAME   = "ESP32-MicKit-101";
static constexpr const char* BLE_FORMAT_STRING = "Peak: %.1f Hz @ %.2f (a.u.) (%s)";

// === BLE connection callback handler ===
class MyServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* server) override {
    bleConnected = true;
    bleAdvertising = false;   // connected => not advertising
    Serial.println("[BLE] Client connected");
  }

  void onDisconnect(BLEServer* server) override {
    bleConnected = false;
    Serial.println("[BLE] Client disconnected");

    // Resume advertising ONLY if the 10s window is still active
    if (bleStopTimer && xTimerIsTimerActive(bleStopTimer) == pdTRUE) {
      server->getAdvertising()->start(); // do NOT restart the timer -> keeps remaining time
      bleAdvertising = true;
      Serial.println("[BLE] Resumed advertising (window still active)");
    } else {
      bleAdvertising = false;
      Serial.println("[BLE] Not resuming advertising (window expired)");
    }
  }
};

// === Stop advertising callback ===
static void bleStopAdvertisingCallback(TimerHandle_t) {
  if (!pServer) return;

  // Window expired now
  bleAdvertising = false;

  if (!bleConnected) {
    pServer->getAdvertising()->stop();
    Serial.println("[BLE] Advertising stopped (timer expired)");
  } else {
    // We were connected; nothing to stop, just mark window closed
    Serial.println("[BLE] Adv window expired while connected");
  }
}

// === Initialization ===
void initBLE() {
  BLEDevice::init(BLE_DEVICE_NAME);

  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService* service = pServer->createService(BLE_SERVICE_UUID);

  pCharacteristic = service->createCharacteristic(
    BLE_CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_NOTIFY
  );
  pCharacteristic->addDescriptor(new BLE2902());

  service->start();

  // Create one-shot timer for stopping advertising
  bleStopTimer = xTimerCreate(
      "BLEStopAdv",
      pdMS_TO_TICKS(BLE_ADV_DURATION_MS),
      pdFALSE,                      // one-shot
      NULL,
      bleStopAdvertisingCallback);

  Serial.println("[BLE] Initialized (idle, no advertising)");
}

// === Start advertising on demand ===
void startBLEAdvertising() {
  if (!pServer) return;

  // Start advertising if not connected and not already advertising
  if (!bleConnected && !bleAdvertising) {
    pServer->getAdvertising()->start();
    bleAdvertising = true;
    Serial.println("[BLE] Advertising started on demand");
  }

  // Restart the one-shot window timer (fresh 10s from now)
  if (bleStopTimer) {
    xTimerStop(bleStopTimer, 0);
    xTimerStart(bleStopTimer, 0);
  }
}

// === Send formatted FFT peak ===
void sendPeakOverBLE(float freq, float magnitude) {
  // If not connected: open an advertising window and return
  if (!bleConnected) {
    startBLEAdvertising();
    Serial.println("[BLE] Waiting for client to connect...");
    return; // Notify will be sent on a subsequent call when connected
  }

  if (!pCharacteristic) {
    Serial.println("[BLE] Characteristic invalid.");
    return;
  }

  // Format timestamp
  time_t now = time(nullptr);
  struct tm timeinfo;
  localtime_r(&now, &timeinfo);

  char timestamp[32];
  strftime(timestamp, sizeof(timestamp), "%H:%M:%S %d/%m/%Y", &timeinfo);

  char msg[96];
  snprintf(msg, sizeof(msg), BLE_FORMAT_STRING, freq, magnitude, timestamp);

  pCharacteristic->setValue(msg);
  pCharacteristic->notify();

  Serial.printf("[BLE] Sent peak: %s\n", msg);
}

bool isBLEConnected() {
  return bleConnected;
}
