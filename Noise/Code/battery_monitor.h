#pragma once
#include <Arduino.h>

#define DEBUG_BATTERY_MONITOR false

// === API ===

// Reads battery and updates voltageOut, percentOut.
// Returns true if read succeeded, false if sensor error.
bool checkBatteryStatus(float& voltageOut, float& percentOut);

// Sets low battery detection thresholds.
void setBatteryLowThreshold(float voltage, float percent);

// Returns true if battery is currently below thresholds.
bool isBatteryLow();

// Enables or disables simulation mode.
void setBatterySimulationMode(bool enable);

// This function must be implemented externally (e.g., in display_manager.cpp)
// to provide actual battery reading logic.
bool readBattery(float& voltageOut, float& percentOut);
