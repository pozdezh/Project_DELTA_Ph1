#include "battery_monitor.h"
#include "display_manager.h"
#include <Arduino.h>
#include <atomic>

// === Internal state ===
static std::atomic<bool> batteryTooLow{false};
static std::atomic<bool> simulateOnly{false};

static float voltageThreshold = 3.40f;
static float percentThreshold = 5.0f;
static const float hysteresis = 0.05f; // 50 mV or 0.5% to avoid chatter

bool checkBatteryStatus(float& voltageOut, float& percentOut) {
  if (simulateOnly.load(std::memory_order_relaxed)) {
    voltageOut = 3.30f;
    percentOut = 3.0f;
    batteryTooLow.store(true, std::memory_order_relaxed);
#if DEBUG_BATTERY_MONITOR
    Serial.println("[BATMON] Simulation mode: forced LOW");
#endif
    return true;
  }

  float voltage = 0.0f, percent = 0.0f;
  bool ok = readBattery(voltage, percent); // Provided by display_manager or sensor driver
  if (!ok) {
#if DEBUG_BATTERY_MONITOR
    Serial.println("[BATMON] Battery check failed");
#endif
    return false;
  }

  voltageOut = voltage;
  percentOut = percent;

#if DEBUG_BATTERY_MONITOR
  Serial.printf("[BATMON] Voltage = %.2f V, Percent = %.1f %%\n", voltage, percent);
#endif

  // Apply thresholds with hysteresis
  bool lowNow = batteryTooLow.load(std::memory_order_relaxed);
  if (!lowNow && (voltage < voltageThreshold || percent < percentThreshold)) {
    batteryTooLow.store(true, std::memory_order_relaxed);
#if DEBUG_BATTERY_MONITOR
    Serial.println("[BATMON] LOW BATTERY detected");
#endif
  } else if (lowNow && (voltage > voltageThreshold + hysteresis &&
                        percent > percentThreshold + 0.5f)) {
    batteryTooLow.store(false, std::memory_order_relaxed);
#if DEBUG_BATTERY_MONITOR
    Serial.println("[BATMON] Battery recovered above thresholds");
#endif
  }

  return true;
}

void setBatteryLowThreshold(float voltage, float percent) {
  voltageThreshold = voltage;
  percentThreshold = percent;
}

bool isBatteryLow() {
  return batteryTooLow.load(std::memory_order_relaxed);
}

void setBatterySimulationMode(bool enable) {
  simulateOnly.store(enable, std::memory_order_relaxed);
}
