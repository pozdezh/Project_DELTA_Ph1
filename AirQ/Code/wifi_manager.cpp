#include "wifi_manager.h"
#include <WiFi.h>
#include <time.h>
#include <atomic>

// NVS (persist last good epoch)
#include "nvs_flash.h"
#include "nvs.h"
#include <sys/time.h>

// ---- Internal flags ----
static std::atomic<bool> wifiConnected{false};
static std::atomic<bool> timeSynced{false};
static std::atomic<bool> mqttConnected{false};  // Placeholder until implemented

// ---- Time sanity floor (same spirit as in fft_logger) ----
// Any epoch below this is considered "not sane" for your deployment window.
static const time_t EPOCH_FLOOR = 1751328000; // 2025-07-31 00:00:00 UTC

// ---- NVS keys for time persistence ----
static const char* NVS_NS  = "time";
static const char* NVS_KEY = "last_epoch";

// Forward decls
static bool nvsInitOnce();
static void saveLastGoodEpoch(time_t t);
static time_t loadLastGoodEpoch();

// === Wi-Fi ===
bool initWiFi() {
    WiFi.mode(WIFI_STA);

    // Initialize NVS and restore last epoch (transparent, best-effort)
    nvsInitOnce();
    time_t last = loadLastGoodEpoch();
    if (last > 0) {
        struct timeval tv = { .tv_sec = last, .tv_usec = 0 };
        settimeofday(&tv, nullptr);
        Serial.printf("[TIME] Restored last good epoch from NVS: %ld\n", (long)last);
    }
    return true;
}

bool connectToWiFi(uint32_t timeoutMs) {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.printf("[WIFI] Connecting to %s...\n", WIFI_SSID);

    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeoutMs) {
        delay(100);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        wifiConnected.store(true, std::memory_order_relaxed);
        Serial.printf("[WIFI] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
        return true;
    } else {
        wifiConnected.store(false, std::memory_order_relaxed);
        Serial.println("[WIFI] Connection failed.");
        return false;
    }
}

bool isWiFiConnected() {
    return wifiConnected.load(std::memory_order_relaxed);
}

bool recoverWiFi(uint32_t timeoutMs) {
    WiFi.disconnect(true);
    wifiConnected.store(false, std::memory_order_relaxed);
    return connectToWiFi(timeoutMs);
}

// === NTP Time ===
bool syncTime(uint32_t timeoutMs) {
    configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, "pool.ntp.org");
    Serial.println("[TIME] Syncing time via NTP...");

    struct tm timeinfo;
    uint32_t start = millis();
    bool ok = false;

    while (!(ok = getLocalTime(&timeinfo)) && (millis() - start) < timeoutMs) {
        delay(100);
    }

    if (ok) {
        timeSynced.store(true, std::memory_order_relaxed);
        time_t now = time(nullptr);
        Serial.println("[TIME] Time sync successful.");
        Serial.printf("[TIME] Current time: %s\n", getFormattedTime().c_str());

        // Persist last good epoch so a cold power loss won’t reset us to garbage
        nvsInitOnce();
        saveLastGoodEpoch(now);
        return true;
    } else {
        timeSynced.store(false, std::memory_order_relaxed);
        Serial.println("[TIME] Time sync failed.");
        return false;
    }
}

bool isTimeSynced() {
    return timeSynced.load(std::memory_order_relaxed);
}

// Optional helper (not required elsewhere, but handy for debug/guards)
bool isTimeSaneNow() {
    return time(nullptr) >= EPOCH_FLOOR;
}

time_t getTimestamp() {
    return time(nullptr);
}

String getFormattedTime() {
    if (!timeSynced.load(std::memory_order_relaxed)) return "TIME NOT SYNCED";

    time_t now = time(nullptr);
    struct tm timeinfo;
    localtime_r(&now, &timeinfo);

    char buffer[32];
    strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", &timeinfo);
    return String(buffer);
}

void disconnectWiFi() {
    WiFi.disconnect(true);
    wifiConnected.store(false, std::memory_order_relaxed);
    // Note: we do NOT clear timeSynced here; time remains valid after Wi-Fi disconnect.
}

// ======== NVS helpers (internal) ========

static bool nvsInitOnce() {
    static bool inited = false;
    if (inited) return true;

    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        // NVS partition was truncated or needs erasing
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    if (err == ESP_OK) {
        inited = true;
        return true;
    }
    Serial.printf("[NVS] Init failed: 0x%04x\n", (uint32_t)err);
    return false;
}

static void saveLastGoodEpoch(time_t t) {
    nvs_handle_t h;
    if (nvs_open(NVS_NS, NVS_READWRITE, &h) == ESP_OK) {
        nvs_set_i64(h, NVS_KEY, (int64_t)t);
        nvs_commit(h);
        nvs_close(h);
#if defined(DEBUG_WIFI_MANAGER) && DEBUG_WIFI_MANAGER
        Serial.printf("[NVS] Saved last epoch: %ld\n", (long)t);
#endif
    } else {
#if defined(DEBUG_WIFI_MANAGER) && DEBUG_WIFI_MANAGER
        Serial.println("[NVS] Open for write failed");
#endif
    }
}

static time_t loadLastGoodEpoch() {
    nvs_handle_t h;
    int64_t v = 0;
    if (nvs_open(NVS_NS, NVS_READONLY, &h) == ESP_OK) {
        esp_err_t e = nvs_get_i64(h, NVS_KEY, &v);
        nvs_close(h);
        if (e == ESP_OK) return (time_t)v;
    }
    return 0;
}

// // === MQTT Placeholders ===
// bool connectToMQTT(uint32_t /*timeoutMs*/) {
//     // TODO: Implement actual MQTT connection
//     mqttConnected.store(true, std::memory_order_relaxed);
//     Serial.println("[MQTT] Placeholder connect — always OK for now");
//     return true;
// }

// bool isMQTTConnected() {
//     return mqttConnected.load(std::memory_order_relaxed);
// }

// bool publishMQTT(const char* topic, const char* payload) {
//     if (!mqttConnected.load(std::memory_order_relaxed)) return false;
//     Serial.printf("[MQTT] Publish [%s] => %s\n", topic, payload);
//     return true;
// }

// bool subscribeMQTT(const char* topic) {
//     if (!mqttConnected.load(std::memory_order_relaxed)) return false;
//     Serial.printf("[MQTT] Subscribe [%s]\n", topic);
//     return true;
// }

// bool recoverMQTT(uint32_t timeoutMs) {
//     mqttConnected.store(false, std::memory_order_relaxed);
//     return connectToMQTT(timeoutMs);
// }

// // === WebSocket Event Handler ===
// static void onWsEvent(AsyncWebSocket* server, AsyncWebSocketClient* client,
//                       AwsEventType type, void* arg, uint8_t* data, size_t len) {
//     switch (type) {
//         case WS_EVT_CONNECT:
//             Serial.printf("[WS] Client %u connected\n", client->id());
//             break;
//         case WS_EVT_DISCONNECT:
//             Serial.printf("[WS] Client %u disconnected\n", client->id());
//             break;
//         default:
//             break;
//     }
// }

// // === HTTP + WebSocket ===
// void startNetworkServices() {
//     if (!LittleFS.begin(true)) {
//         Serial.println("[LittleFS] Mount failed");
//         return;
//     }

//     Serial.println("[LittleFS] Mount successful");
//     server.serveStatic("/", LittleFS, "/").setDefaultFile("index.html");

//     ws.onEvent(onWsEvent);
//     server.addHandler(&ws);

//     server.begin();
//     Serial.println("[WIFI] HTTP + WebSocket server started");

//     // WS upkeep task
//     xTaskCreatePinnedToCore(wsMaintenanceTask, "WS_Maint", 2048, NULL, 1, NULL, 1);
// }

// // === WebSocket send helpers ===
// void sendWAVBuffer(const uint8_t* data, size_t len) {
//     if (!data || len == 0 || ws.count() == 0) return;
//     ws.binaryAll(data, len);
//     Serial.printf("[WS] Sent %u bytes to %u client(s)\n", len, ws.count());
// }

// void sendFFTFrame(const float* freqs, const float* mags, size_t count) {
//     if (!freqs || !mags || count == 0 || ws.count() == 0) return;

//     size_t totalSize = count * 2 * sizeof(float);
//     uint8_t* buffer = (uint8_t*)heap_caps_malloc(totalSize, MALLOC_CAP_8BIT);
//     if (!buffer) return;

//     float* fbuf = (float*)buffer;
//     for (size_t i = 0; i < count; ++i) {
//         fbuf[2 * i] = freqs[i];
//         fbuf[2 * i + 1] = mags[i];
//     }

//     ws.binaryAll(buffer, totalSize);
//     Serial.printf("[WS] Sent FFT frame: %u bins, %u bytes\n", (unsigned)count, (unsigned)totalSize);
//     free(buffer);
// }

// void updateWebSocket() {
//     ws.cleanupClients();
// }

// // === WebSocket maintenance task ===
// static void wsMaintenanceTask(void* param) {
//     for (;;) {
//         updateWebSocket();
//         vTaskDelay(pdMS_TO_TICKS(50));
//     }
// }
