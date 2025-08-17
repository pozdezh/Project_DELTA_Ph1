#include "display_manager.h"
#include <Wire.h>
#include "Adafruit_GFX.h"
#include "Adafruit_ST7735.h"
#include "signal_config.h"
#include <atomic>
#include <math.h>    // for isnan

// === Debug toggle ===
#define DEBUG_DISPLAY_MANAGER false

// === Internal state ===
Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_RST);
static Adafruit_MAX17048* maxlipo = nullptr;
static std::atomic<bool> displayActive{false};

// Keep track of whether the fuel gauge has been primed (quickStart done) for the
// *current powered-on session* of the STEMMA rail.
static bool gaugePrimed = false;

// === Power control ===
static inline void setStemmaPower(bool on) {
  digitalWrite(STEMMA_PIN, on ? HIGH : LOW);
#if DEBUG_DISPLAY_MANAGER
  Serial.printf("[DISPLAY] STEMMA power %s\n", on ? "ON" : "OFF");
#endif
}

void setDisplayActive(bool active) {
  displayActive.store(active, std::memory_order_relaxed);
}

bool isDisplayActive() {
  return displayActive.load(std::memory_order_relaxed);
}

void setBatteryMonitor(Adafruit_MAX17048* batteryRef) {
  maxlipo = batteryRef;
}

// Read battery with sane fuel-gauge handling:
// - Power the STEMMA rail ON.
// - Run quickStart() only once per powered session (not every read).
// - Give the gauge a short settle before reading.
// - If no UI is showing, power the rail OFF immediately after the read.
// - If UI is showing (button flow), keep the rail ON until the screen turns off.
bool readBattery(float& voltageOut, float& percentOut) {
  if (!maxlipo) {
#if DEBUG_DISPLAY_MANAGER
    Serial.println("[BATTERY] Fuel gauge not set");
#endif
    return false;
  }

  // Ensure the rail is powered for the measurement.
  setStemmaPower(true);

  // Prime the gauge once per power-on session.
  if (!gaugePrimed) {
    delay(200);             // allow I2C device to wake
    maxlipo->quickStart();  // one-time per session
    delay(200);             // let the algorithm settle briefly
    gaugePrimed = true;
  } else {
    // Small settle between consecutive reads within a session
    delay(10);
  }

  // Take two reads and use the second for a bit more stability.
  (void)maxlipo->cellVoltage();
  (void)maxlipo->cellPercent();
  delay(200);
  voltageOut = maxlipo->cellVoltage();
  percentOut = maxlipo->cellPercent();

  if (isnan(voltageOut) || isnan(percentOut)) {
#if DEBUG_DISPLAY_MANAGER
    Serial.println("[BATTERY] Invalid reading (NaN)");
#endif
    // If this was a background read, power down the rail again.
    if (!isDisplayActive()) { setStemmaPower(false); gaugePrimed = false; }
    return false;
  }

  // For background (non-UI) reads, save power by turning the rail off immediately.
  if (!isDisplayActive()) {
    setStemmaPower(false);
    gaugePrimed = false;
  }

  return true;
}

void initDisplay() {
  pinMode(BACKLIGHT_PIN, OUTPUT);
  digitalWrite(BACKLIGHT_PIN, LOW);

  pinMode(STEMMA_PIN, OUTPUT);
  setStemmaPower(false);
  gaugePrimed = false;

  tft.initR(INITR_MINI160x80_PLUGIN);
  tft.setRotation(1);
  tft.setTextWrap(false);
  tft.fillScreen(ST77XX_BLACK);
  tft.setTextColor(ST77XX_WHITE);

#if DEBUG_DISPLAY_MANAGER
  Serial.println("[DISPLAY] Initialized");
#endif
}

void showBatteryInfo(float voltage, float percent) {
  displayActive.store(true, std::memory_order_relaxed);
  turnOnBacklight();
  tft.fillScreen(ST77XX_BLACK);

  tft.setCursor(10, 20);
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_WHITE);
  tft.print("BatteryP: ");
  tft.setCursor(80, 20);
  tft.print(percent, 1);
  tft.print(" %");

  tft.setCursor(10, 50);
  tft.print("BatteryV: ");
  tft.setCursor(80, 50);
  tft.print(voltage, 2);
  tft.print(" V");
}

void showBatteryBusy() {
  displayActive.store(true, std::memory_order_relaxed);
  turnOnBacklight();
  tft.fillScreen(ST77XX_BLACK);
  tft.setCursor(10, 40);
  tft.setTextColor(ST77XX_YELLOW);
  tft.setTextSize(1);
  tft.println("Battery busy...");
}

void showShutdownWarning(float voltage) {
  displayActive.store(true, std::memory_order_relaxed);
  turnOnBacklight();
  tft.fillScreen(ST77XX_BLACK);

  tft.setTextColor(ST77XX_RED);
  tft.setTextSize(2);
  tft.setCursor(10, 30);
  tft.println("Battery LOW");

  tft.setTextSize(1);
  tft.setCursor(10, 60);
  tft.printf("%.2f V\n", voltage);
  tft.setCursor(10, 80);
  tft.println("Shutting down...");
}

void turnOnBacklight() {
  digitalWrite(BACKLIGHT_PIN, HIGH);
#if DEBUG_DISPLAY_MANAGER
  Serial.println("[DISPLAY] Backlight ON");
#endif
}

void turnOffBacklight() {
  digitalWrite(BACKLIGHT_PIN, LOW);
  tft.fillScreen(ST77XX_BLACK);

  // When the UI turns off, power down the sensor rail and reset priming.
  setStemmaPower(false);
  gaugePrimed = false;

  displayActive.store(false, std::memory_order_relaxed);
#if DEBUG_DISPLAY_MANAGER
  Serial.println("[DISPLAY] Backlight OFF");
#endif
}
