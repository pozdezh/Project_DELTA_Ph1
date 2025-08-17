#include <Arduino.h>
#include "signal_config.h"
#include "esp_pm.h"
#include "esp_sleep.h"
#include "esp_system.h"   // FIX: for esp_restart()

#include "audio_sampler.h"
#include "fft_engine.h"
#include "fft_logger.h"
#include "button_handler.h"
#include "battery_monitor.h"
#include "display_manager.h"
#include "wifi_manager.h"
#include "ble_fft.h"
#include "Adafruit_MAX1704X.h"
#include <time.h>   // <-- ensure time_t / time() available

// === Config ===
#define CYCLE_PERIOD_MS         1500
#define TIME_SYNC_INTERVAL_SEC  (12 * 3600)

// AUTO battery check interval
#define BATTERY_AUTOCHECK_INTERVAL_MS  (5UL * 60UL * 1000UL)  // 5 minutes

// FIX: initial sync policy — reboot if these many rounds fail
#define INIT_SYNC_MAX_ROUNDS            3
#define INIT_SYNC_WIFI_TRIES_PER_ROUND  3
#define INIT_SYNC_NTP_TRIES_PER_ROUND   3
#define INIT_SYNC_ROUND_BACKOFF_MS      (30000)   // 30s between rounds

// === RTC persisted ===
RTC_DATA_ATTR time_t lastSyncTime = 0;
RTC_DATA_ATTR time_t lastSyncAttempt = 0;
RTC_DATA_ATTR uint8_t initSyncFailCount = 0;   // unused for reboot policy, kept for compatibility

// === RTOS handles ===
TaskHandle_t samplerTaskHandle;
TaskHandle_t fftTaskHandle;
TaskHandle_t loggerTaskHandle;
TaskHandle_t batteryTaskHandle;
TimerHandle_t cycleTimer;
TimerHandle_t displayTimer;

// === FFT queue ===
struct FFTFrame {
  float* frequencies;
  float* magnitudes;
  size_t count;
};
QueueHandle_t fftQueue;
#define FFT_QUEUE_LENGTH 4

// === Cycle timing diagnostics ===
static volatile uint32_t g_lastSampleMs = 0;
static volatile uint32_t g_lastFFTMs    = 0;
static volatile uint32_t g_lastLogMs    = 0;

// === Timer callbacks ===
void IRAM_ATTR onCycleTimer(TimerHandle_t) {
  BaseType_t high = pdFALSE;
  vTaskNotifyGiveFromISR(samplerTaskHandle, &high);
  if (high == pdTRUE) {
    portYIELD_FROM_ISR();
  }
}

void turnOffDisplayCallback(TimerHandle_t) {
  turnOffBacklight();
  setDisplayActive(false);
}

// === Prepare for Deep Sleep (no BLE power-off here) ===
static void prepareForDeepSleep() {
  Serial.println("[PWR] Preparing for deep sleep...");

  // Stop timers
  if (cycleTimer)   xTimerStop(cycleTimer, 0);
  if (displayTimer) xTimerStop(displayTimer, 0);

  // Display & sensor rail
  turnOffBacklight();
  setDisplayActive(false);
  pinMode(STEMMA_PIN, OUTPUT);
  digitalWrite(STEMMA_PIN, LOW);      // cut sensor rail

  // SD bus to benign state
  pinMode(SD_CS, OUTPUT);
  digitalWrite(SD_CS, HIGH);
  pinMode(SD_MOSI, INPUT);
  pinMode(SD_SCK,  INPUT);
  pinMode(SD_MISO, INPUT);

  // Deinit heavy modules (optional but safe)
  deinitFFTLogger();
  deinitFFTEngine();

  vTaskDelay(pdMS_TO_TICKS(50));
  Serial.println("[PWR] Entering deep sleep...");
}

// === Initial time sync with limited rounds; reboot on failure ===
// FIX: replaces the previous "retry forever" block. Only runs at boot.
static void tryInitialTimeSyncOrReboot() {
  initSyncFailCount = 0; // avoid inheriting any old backoff idea

  for (int round = 1; round <= INIT_SYNC_MAX_ROUNDS; ++round) {
    Serial.printf("[TIME] Initial sync — round %d/%d\n", round, INIT_SYNC_MAX_ROUNDS);
    lastSyncAttempt = time(nullptr);

    bool wifiOK = false;

    // Wi-Fi attempts this round
    for (int wifiTry = 1; wifiTry <= INIT_SYNC_WIFI_TRIES_PER_ROUND && !wifiOK; ++wifiTry) {
      if (connectToWiFi(8000)) {
        Serial.printf("[WIFI] Connected (init) on attempt %d\n", wifiTry);
        wifiOK = true;

        // NTP attempts this round (only if Wi-Fi connected)
        bool ntpOK = false;
        for (int ntpTry = 1; ntpTry <= INIT_SYNC_NTP_TRIES_PER_ROUND && !ntpOK; ++ntpTry) {
          if (syncTime(6000)) {
            lastSyncTime = time(nullptr);
            Serial.printf("[TIME] Initial sync OK: %s\n", getFormattedTime().c_str());
            disconnectWiFi();
            return; // success -> exit function, continue boot
          }
          Serial.printf("[TIME] NTP (init) attempt %d failed\n", ntpTry);
          vTaskDelay(pdMS_TO_TICKS(300));
        }

        // NTP failed this round; disconnect and break to next round/backoff
        disconnectWiFi();
        break;
      } else {
        Serial.printf("[WIFI] (init) attempt %d failed\n", wifiTry);
        vTaskDelay(pdMS_TO_TICKS(800));
      }
    }

    // If we reach here, this round failed; backoff before next round if any
    if (round < INIT_SYNC_MAX_ROUNDS) {
      Serial.printf("[TIME] Initial sync round %d failed — backoff %lu ms\n",
                    round, (unsigned long)INIT_SYNC_ROUND_BACKOFF_MS);
      uint32_t ms = INIT_SYNC_ROUND_BACKOFF_MS;
      while (ms > 0) {
        vTaskDelay(pdMS_TO_TICKS(250));
        ms = (ms > 250) ? (ms - 250) : 0;
      }
    }
  }

  // All rounds failed — reboot on boot-time policy
  Serial.println("[TIME] Initial sync failed after all rounds — rebooting.");
  vTaskDelay(pdMS_TO_TICKS(100));
  esp_restart();
}

// === Periodic 12h maintenance sync (non-blocking; failures are tolerated) ===
static void tryPeriodicTimeSync() {
  time_t now = time(nullptr);
  if (lastSyncTime == 0) return; // only after a successful initial sync

  if ((uint32_t)(now - lastSyncTime) < TIME_SYNC_INTERVAL_SEC) return;

  Serial.println("[TIME] 12h maintenance time sync — attempting...");

  bool synced = false;
  for (int wifiTry = 1; wifiTry <= 2 && !synced; ++wifiTry) {
    if (connectToWiFi(6000)) {
      for (int ntpTry = 1; ntpTry <= 2 && !synced; ++ntpTry) {
        if (syncTime(4000)) {
          lastSyncTime = time(nullptr);
          Serial.printf("[TIME] Maintenance sync OK: %s\n", getFormattedTime().c_str());
          synced = true;
          break;
        }
        vTaskDelay(pdMS_TO_TICKS(200));
      }
      disconnectWiFi();
    }
  }

  if (!synced) {
    Serial.println("[TIME] Maintenance sync failed — keeping previous time; will retry later.");
  }
}

void samplerTask(void*) {
  if (!initSampler(xTaskGetCurrentTaskHandle())) {
    Serial.println("[FATAL] Sampler init failed");
    vTaskDelete(nullptr);
  }

  static uint32_t lastAutoCheckMs = 0;

  for (;;) {
    // Wait for cycle start
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    uint32_t cycleStart = millis();

    // Periodic time sync (non-blocking)
    tryPeriodicTimeSync();

    // --- Sampling timing ---
    uint32_t tS0 = millis();
    Serial.println("\n[CYCLE] Sampling started");
    beginSamplingAsync();
    while (!pollSampler()) {
      // Keep core responsive; don’t consume task notifications here
      vTaskDelay(pdMS_TO_TICKS(1));
    }
    g_lastSampleMs = millis() - tS0;
    Serial.printf("[ADC] Samples: %lu | t=%lums\n", getSampleCount(), g_lastSampleMs);

    // Hand off to FFT and wait for logger completion
    xTaskNotifyGive(fftTaskHandle);
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);  // wait for logger done
    // g_lastFFTMs and g_lastLogMs are updated in their respective tasks

    // === Periodic background battery check ===
    uint32_t nowMs = millis();
    if ((nowMs - lastAutoCheckMs) >= BATTERY_AUTOCHECK_INTERVAL_MS) {
      lastAutoCheckMs = nowMs;  // update early to avoid drift on long checks

      // Skip background check while the on-screen battery UI is active.
      if (!isDisplayActive()) {
        float v = 0.0f, p = 0.0f;
        if (checkBatteryStatus(v, p)) {
          Serial.printf("[BATMON] Auto-check: V=%.3fV, %%=%.1f\n", v, p);
          if (isBatteryLow()) {
            showShutdownWarning(v);
            vTaskDelay(pdMS_TO_TICKS(2000));
            prepareForDeepSleep();
            esp_deep_sleep_start();
          }
        } else {
          Serial.println("[BATMON] Auto-check failed (readBattery).");
        }
        // STEMMA power handling is internal to checkBatteryStatus()/display manager.
      } else {
        Serial.println("[BATMON] Skipped auto-check (UI active).");
      }
    }

    // --- Pad to cycle, print duty breakdown ---
    uint32_t elapsed  = millis() - cycleStart;
    uint32_t sampleMs = g_lastSampleMs;
    uint32_t fftMs    = g_lastFFTMs;
    uint32_t logMs    = g_lastLogMs;
    uint32_t activeMs = sampleMs + fftMs + logMs;

    if (elapsed < CYCLE_PERIOD_MS) {
      uint32_t idleMs = CYCLE_PERIOD_MS - elapsed;
      float dutyTotal  = 100.0f * activeMs / CYCLE_PERIOD_MS;
      float dutySample = 100.0f * sampleMs / CYCLE_PERIOD_MS;
      float dutyFFT    = 100.0f * fftMs    / CYCLE_PERIOD_MS;
      float dutyLog    = 100.0f * logMs    / CYCLE_PERIOD_MS;
      float dutyIdle   = 100.0f * idleMs   / CYCLE_PERIOD_MS;

      Serial.printf("[DUTY] total=%.1f%% (active=%lums/%ums) | sample=%lums (%.1f%%), fft=%lums (%.1f%%), log=%lums (%.1f%%), idle≈%lums (%.1f%%)\n",
                    dutyTotal, activeMs, (unsigned)CYCLE_PERIOD_MS,
                    sampleMs, dutySample, fftMs, dutyFFT, logMs, dutyLog, idleMs, dutyIdle);

      vTaskDelay(pdMS_TO_TICKS(idleMs));   // allow light sleep
    } else {
      float dutyTotal = 100.0f * activeMs / CYCLE_PERIOD_MS;
      Serial.printf("[DUTY] Overrun: total≈%.1f%% (active≈%lums > %ums)\n",
                    dutyTotal, activeMs, (unsigned)CYCLE_PERIOD_MS);
    }
  }
}



// === FFT Task ===
void fftTask(void*) {
  if (!initFFTEngine()) {
    Serial.println("[FATAL] FFT init failed");
    vTaskDelete(nullptr);
  }
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

    const uint16_t* raw = getReadySamples();
    size_t count = getSampleCount();

    uint32_t tF0 = millis();

    float* volts = (float*)heap_caps_malloc(sizeof(float) * count, MALLOC_CAP_SPIRAM);
    if (!volts || !convertRawToMV(raw, volts, count)) {
      if (volts) free(volts);
      g_lastFFTMs = millis() - tF0;
      continue;
    }

    if (processFFT(volts, count)) {
      FFTFrame* frame = (FFTFrame*)heap_caps_malloc(sizeof(FFTFrame), MALLOC_CAP_SPIRAM);
      if (!frame) { free(volts); g_lastFFTMs = millis() - tF0; continue; }
      frame->frequencies = (float*)heap_caps_malloc(sizeof(float) * FFT_BINS, MALLOC_CAP_SPIRAM);
      frame->magnitudes  = (float*)heap_caps_malloc(sizeof(float) * FFT_BINS, MALLOC_CAP_SPIRAM);
      frame->count = FFT_BINS;
      if (!frame->frequencies || !frame->magnitudes) {
        if (frame->frequencies) free(frame->frequencies);
        if (frame->magnitudes)  free(frame->magnitudes);
        free(frame);
        free(volts);
        g_lastFFTMs = millis() - tF0;
        continue;
      }
      memcpy(frame->frequencies, getFFTFrequencies(), sizeof(float) * FFT_BINS);
      memcpy(frame->magnitudes,  getFFTMagnitudes(), sizeof(float) * FFT_BINS);
      free(volts);
      g_lastFFTMs = millis() - tF0;

      if (xQueueSend(fftQueue, &frame, pdMS_TO_TICKS(10)) != pdPASS) {
        free(frame->frequencies);
        free(frame->magnitudes);
        free(frame);
      }
    } else {
      free(volts);
      g_lastFFTMs = millis() - tF0;
    }
  }
}

// === Logger Task ===
void loggerTask(void*) {
  FFTFrame* frame = nullptr;
  uint32_t lastRetryMs = 0;

  for (;;) {
    // If SD not ready, try to init every ~500 ms
    if (!isLoggerReady()) {
      uint32_t now = millis();
      if (now - lastRetryMs >= 500) {
        Serial.println("[LOGGER] SD not ready — attempting init...");
        deinitFFTLogger();
        vTaskDelay(pdMS_TO_TICKS(100));
        initFFTLogger();
        lastRetryMs = now;
      }
    }

    if (xQueueReceive(fftQueue, &frame, portMAX_DELAY) == pdTRUE && frame) {
      uint32_t tL0 = millis();
      bool ok = false;

      if (isLoggerReady()) {
        ok = saveFFTFrame(frame->frequencies, frame->magnitudes, frame->count);

        if (!ok) {
          Serial.println("[LOGGER] Save failed, attempting clean reinit...");
          deinitFFTLogger();
          vTaskDelay(pdMS_TO_TICKS(200));
          if (initFFTLogger()) {
            tL0 = millis();
            ok = saveFFTFrame(frame->frequencies, frame->magnitudes, frame->count);
          }
        }
      } else {
        Serial.println("[LOGGER] SD not ready — skipping frame.");
      }

      g_lastLogMs = millis() - tL0;

      // Free frame regardless to avoid leaks
      free(frame->frequencies);
      free(frame->magnitudes);
      free(frame);

      // Notify sampler so the cycle continues
      xTaskNotifyGive(samplerTaskHandle);
    }
  }
}

// === Battery Task (STEMMA rail handled inside battery_monitor) ===
void batteryTask(void*) {
  float voltage = 0.0f, percent = 0.0f;

  for (;;) {
    if (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(50)) > 0) {
      if (!isDisplayActive() && isBatteryRequestPending()) {
        clearBatteryRequest();
        setDisplayActive(true);

        // STEMMA power is now managed inside checkBatteryStatus()
        if (checkBatteryStatus(voltage, percent)) {
          showBatteryInfo(voltage, percent);

          if (isFFTReady()) {
            float peakMag = 0.0f;
            float peakFreq = getDominantFrequency(peakMag);
            sendPeakOverBLE(peakFreq, peakMag);
          }

          if (isBatteryLow()) {
            showShutdownWarning(voltage);
            vTaskDelay(pdMS_TO_TICKS(2000));
            prepareForDeepSleep();
            esp_deep_sleep_start();
          }
        } else {
          showBatteryBusy();
        }

        // Auto turn-off backlight after a short delay
        xTimerStart(displayTimer, 0);
      }
    }
    // Always poll button events to trigger battery screen
    pollButton();
  }
}


// === Setup ===
void setup() {
  Serial.begin(115200);
  vTaskDelay(pdMS_TO_TICKS(500));
  Serial.println("[BOOT] MicKit RTOS Patched");

  esp_pm_config_esp32s3_t pm_cfg = {
    .max_freq_mhz = 240,
    .min_freq_mhz = 10,     // 10 MHz idle (your previous setting)
    .light_sleep_enable = true
  };
  esp_pm_configure(&pm_cfg);

  initDisplay();
  static Adafruit_MAX17048 battery;
  battery.begin();
  setBatteryMonitor(&battery);
  setBatteryLowThreshold(3.40f, 5.0f);
  initButton();
  initBLE();

  displayTimer = xTimerCreate("DispOff", pdMS_TO_TICKS(2000), pdFALSE, NULL, turnOffDisplayCallback);
  cycleTimer   = xTimerCreate("Cycle",   pdMS_TO_TICKS(CYCLE_PERIOD_MS), pdTRUE,  NULL, onCycleTimer);

  fftQueue = xQueueCreate(FFT_QUEUE_LENGTH, sizeof(FFTFrame*));
  if (!fftQueue) {
    Serial.println("[FATAL] FFT queue creation failed");
    while (true) { vTaskDelay(pdMS_TO_TICKS(1000)); }
  }

  // ====== Initial time sync — limited rounds, reboot on failure ======
  tryInitialTimeSyncOrReboot();

  // >>> NEW: explicit confirmation that time is valid before any logging <<<
  Serial.printf("[TIME] Ready at boot: %s\n", getFormattedTime().c_str());

  // ====== Start tasks and timer after time is valid ======
  xTaskCreatePinnedToCore(samplerTask, "Sampler", 4096, NULL, 3, &samplerTaskHandle, 0);
  xTaskCreatePinnedToCore(fftTask,     "FFT",     4096, NULL, 2, &fftTaskHandle,    0);
  xTaskCreatePinnedToCore(loggerTask,  "Logger",  4096, NULL, 1, &loggerTaskHandle, 0);
  xTaskCreatePinnedToCore(batteryTask, "Battery", 4096, NULL, 1, &batteryTaskHandle,0);
  setBatteryTaskHandle(batteryTaskHandle);

  xTimerStart(cycleTimer, 0);

  Serial.printf("[MEM] Heap: %u | PSRAM: %u\n",
                heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                heap_caps_get_free_size(MALLOC_CAP_SPIRAM));

  vTaskDelete(nullptr);
}

void loop() {
  // RTOS driven
}
