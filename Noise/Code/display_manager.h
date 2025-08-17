#pragma once
#include <Arduino.h>
#include "Adafruit_MAX1704X.h"

// === API ===
void initDisplay();

void setDisplayActive(bool active);
bool isDisplayActive();

void setBatteryMonitor(Adafruit_MAX17048* batteryRef);

// Reads battery voltage and percent from MAX17048
bool readBattery(float& voltageOut, float& percentOut);

// UI functions
void showBatteryInfo(float voltage, float percent);
void showBatteryBusy();
void showShutdownWarning(float voltage);

// Backlight control
void turnOnBacklight();
void turnOffBacklight();
