#pragma once
#include <Arduino.h>

// === Configuration ===
#define DEBUG_BUTTON_EVENTS false  // Set to true to enable Serial debug prints

// Default debounce and cooldown values (overridable at compile time)
#ifndef DEBOUNCE_WINDOW
#define DEBOUNCE_WINDOW 50    // Button debounce time in milliseconds
#endif

#ifndef COOLDOWN_WINDOW
#define COOLDOWN_WINDOW 200   // Minimum time between accepted presses (ms)
#endif

// === API ===
void setBatteryTaskHandle(TaskHandle_t handle);
void initButton();                            // Initialize GPIO and ISR
void pollButton();                            // Call periodically to handle debounce

bool isBatteryRequestPending();               // True if battery display was requested
void clearBatteryRequest();                   // Clear the pending request

void setButtonDebounce(uint16_t ms);          // Change debounce duration at runtime
void setButtonCooldown(uint16_t ms);          // Change cooldown period at runtime

void IRAM_ATTR handleButtonISR();             // Interrupt handler for button press

