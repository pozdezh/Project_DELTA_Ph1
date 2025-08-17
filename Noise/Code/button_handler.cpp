#include "button_handler.h"
#include "signal_config.h"
#include <atomic>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static std::atomic<bool> buttonISRTriggered{false};
static std::atomic<bool> batteryRequestPending{false};

static uint16_t debounceWindow = DEBOUNCE_WINDOW;
static uint16_t cooldownWindow = COOLDOWN_WINDOW;

static TaskHandle_t batteryTaskHandle = nullptr;

void setBatteryTaskHandle(TaskHandle_t handle) {
  batteryTaskHandle = handle;
#if DEBUG_BUTTON_EVENTS
  Serial.printf("[BUTTON] Battery task handle set: %p\n", handle);
#endif
}

void IRAM_ATTR handleButtonISR() {
  if (!buttonISRTriggered.load(std::memory_order_relaxed)) {
    buttonISRTriggered.store(true, std::memory_order_relaxed);
  }
}

void initButton() {
  static bool initialized = false;
  if (initialized) return;

  pinMode(BUTTON_PIN, INPUT_PULLDOWN);
  attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), handleButtonISR, RISING);
  initialized = true;
}

void pollButton() {
  static unsigned long lastTriggerTime = 0;
  static unsigned long lastPressAccepted = 0;
  static bool debounceInProgress = false;

  unsigned long now = millis();

  if (buttonISRTriggered.exchange(false, std::memory_order_relaxed)) {
    if (!debounceInProgress) {
      lastTriggerTime = now;
      debounceInProgress = true;
    }
  }

  if (debounceInProgress && (now - lastTriggerTime >= debounceWindow)) {
    debounceInProgress = false;

    if (digitalRead(BUTTON_PIN) == HIGH &&
        (now - lastPressAccepted > cooldownWindow)) {

      lastPressAccepted = now;
      batteryRequestPending.store(true, std::memory_order_relaxed);

      if (batteryTaskHandle) {
        xTaskNotifyGive(batteryTaskHandle);
      }

#if DEBUG_BUTTON_EVENTS
      Serial.printf("[BUTTON] Press accepted at %lu ms\n", now);
#endif
    }
  }
}

bool isBatteryRequestPending() {
  return batteryRequestPending.load(std::memory_order_relaxed);
}

void clearBatteryRequest() {
  batteryRequestPending.store(false, std::memory_order_relaxed);
}

void setButtonDebounce(uint16_t ms) {
  debounceWindow = ms;
}

void setButtonCooldown(uint16_t ms) {
  cooldownWindow = ms;
}

