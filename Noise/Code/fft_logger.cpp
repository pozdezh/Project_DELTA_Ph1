#include "fft_logger.h"
#include <SD.h>
#include <SPI.h>
#include <time.h>
#include "signal_config.h"
#include "esp_heap_caps.h"
#include "fft_engine.h"
#include <SdFat.h>
#include <sdios.h>

// NEW: require time sync
#include "wifi_manager.h"   // isTimeSynced(), getFormattedTime()

// === Debug toggle ===
#define DEBUG_FFT_LOGGER true

// === Config ===
#define MAX_LOG_FILE_SIZE (500UL * 1024UL * 1024UL) // 500 MB max per file

static bool sdReady = false;
static File logFile;
static uint32_t logOffset = 0;
static const char* indexFile = "/log_idx.txt";
static const char* fileIndexFile = "/log_file_idx.txt";
static uint8_t* logBuffer = nullptr;
static size_t logBufferSize = 0;
static uint16_t logFileIndex = 0;

static uint8_t sectorBuffer[512];
static LoggerStatus loggerStatus = LoggerStatus::NOT_READY;

// ===== Time sanity gate (prevents writing with stale/undefined RTC) =====
static const time_t MIN_VALID_EPOCH = 1751328000; // 2025-07-31 00:00:00 UTC (pick any safe floor)

static inline bool timeIsSane() {
  time_t now = time(nullptr);
  // require BOTH: NTP flag set and epoch beyond a reasonable floor
  return isTimeSynced() && (now >= MIN_VALID_EPOCH);
}

// ===== Helpers =====

// FIX: atomic (truncate) number write via temp+rename
static inline void atomicWriteUL(const char* path, const char* tmpPath, unsigned long v) {
  if (File t = SD.open(tmpPath, FILE_WRITE)) {
    t.printf("%lu\n", v);
    t.close();
    SD.remove(path);
    SD.rename(tmpPath, path);
  }
}
static inline void atomicWriteU16(const char* path, const char* tmpPath, uint16_t v) {
  if (File t = SD.open(tmpPath, FILE_WRITE)) {
    t.printf("%u\n", v);
    t.close();
    SD.remove(path);
    SD.rename(tmpPath, path);
  }
}

// FIX: robust read of a single integer (returns false if not present/invalid)
static bool readUL(const char* path, unsigned long& out) {
  File f = SD.open(path, FILE_READ);
  if (!f) return false;
  String s = f.readString(); // read all; avoids parseInt() stopping at first stale "0\n"
  f.close();
  // find last integer in the string (handles accidental multiple lines)
  long last = -1;
  int i = s.length() - 1;
  // skip non-digits/newlines
  while (i >= 0 && !(s[i] >= '0' && s[i] <= '9')) i--;
  if (i < 0) return false;
  int end = i;
  while (i >= 0 && (s[i] >= '0' && s[i] <= '9')) i--;
  String num = s.substring(i + 1, end + 1);
  last = num.toInt();
  if (last < 0) return false;
  out = (unsigned long)last;
  return true;
}
static bool readU16(const char* path, uint16_t& out) {
  unsigned long tmp;
  if (!readUL(path, tmp)) return false;
  if (tmp > 0xFFFFUL) return false;
  out = (uint16_t)tmp;
  return true;
}

// --- Small helper: persist current index state ---
// FIX: make writes atomic and truncating
static inline void persistIndices() {
  atomicWriteUL(indexFile, "/log_idx.tmp", (unsigned long)logOffset);
  atomicWriteU16(fileIndexFile, "/log_file_idx.tmp", logFileIndex);
}

// === Internal helper to open log file with rolling index ===
static bool openLogFile() {
  char fname[32];
  snprintf(fname, sizeof(fname), "/LOG_%04u.BIN", logFileIndex);
  // NOTE: FILE_WRITE creates if missing and appends; we will seek() after reconciling offset.
  logFile = SD.open(fname, FILE_WRITE);
  if (!logFile) {
    Serial.printf("[SD] Failed to open log file %s\n", fname);
    loggerStatus = LoggerStatus::FILE_OPEN_FAILED;
    return false;
  }
#if DEBUG_FFT_LOGGER
  Serial.printf("[SD] Opened log file: %s\n", fname);
#endif
  return true;
}

// NEW: discover highest existing /LOG_XXXX.BIN and its size
static bool findHighestLogFile(uint16_t& outIndex, uint32_t& outSize) {
  File root = SD.open("/");
  if (!root) return false;

  bool found = false;
  uint16_t best = 0;
  uint32_t bestSize = 0;

  for (File f = root.openNextFile(); f; f = root.openNextFile()) {
    const char* nm = f.name();  // ex: "/LOG_0007.BIN"
    if (!nm) continue;
    // strict match: "/LOG_", 4 digits, ".BIN"
    if (strlen(nm) == 13 && strncmp(nm, "/LOG_", 5) == 0 && strcasecmp(nm + 9, ".BIN") == 0) {
      char buf[5] = { nm[5], nm[6], nm[7], nm[8], 0 };
      int idx = atoi(buf);
      if (idx >= 0 && idx <= 0xFFFF) {
        if (!found || idx > best) {
          found = true;
          best = (uint16_t)idx;
          bestSize = f.size();
        }
      }
    }
  }
  if (found) { outIndex = best; outSize = bestSize; }
  return found;
}

// NEW: check if a specific /LOG_XXXX.BIN exists and (optionally) get its size
static bool getLogFileSizeIfExists(uint16_t idx, uint32_t& outSize) {
  char fname[32];
  snprintf(fname, sizeof(fname), "/LOG_%04u.BIN", idx);
  File f = SD.open(fname, FILE_READ);
  if (!f) return false;
  outSize = f.size();
  f.close();
  return true;
}

void deinitFFTLogger() {
  if (logFile) {
    logFile.flush();
    logFile.close();
  }
  sdReady = false;
  logOffset = 0;

  if (logBuffer) {
    free(logBuffer);
    logBuffer = nullptr;
    logBufferSize = 0;
  }

  // --- fully release the bus so hot-insert works reliably ---
  pinMode(SD_CS, OUTPUT);
  digitalWrite(SD_CS, HIGH);     // deselect card
  pinMode(SD_MOSI, INPUT);
  pinMode(SD_SCK,  INPUT);
  pinMode(SD_MISO, INPUT);
  SD.end();
  SPI.end();
  delay(50);

  loggerStatus = LoggerStatus::NOT_READY;
}

bool recoverFFTLogger() {
  deinitFFTLogger();
  return initFFTLogger();
}

bool initFFTLogger() {
  if (sdReady) return true;

  SPI.begin(SD_SCK, SD_MISO, SD_MOSI, SD_CS);
  Serial.println("[SD] Initializing card...");
  delay(100);

  for (int i = 0; i < 3; ++i) {
    if (SD.begin(SD_CS, SPI, 25000000)) {
      sdReady = true;

      // Allocate persistent buffer for maximum possible frame size
      logBufferSize = ((32 + (FFT_BINS * 2 * sizeof(float)) + 511) / 512) * 512;
      logBuffer = (uint8_t*)heap_caps_malloc(logBufferSize, MALLOC_CAP_SPIRAM);
      if (!logBuffer) {
        Serial.println("[SD] Failed to allocate persistent log buffer");
        deinitFFTLogger();
        loggerStatus = LoggerStatus::BUFFER_ALLOC_FAILED;
        return false;
      }

      uint8_t type = SD.cardType();
      Serial.print("[SD] Card type: ");
      switch (type) {
        case CARD_NONE:
          Serial.println("None");
          loggerStatus = LoggerStatus::SD_INIT_FAILED;
          sdReady = false;
          return false;
        case CARD_MMC:   Serial.println("MMC"); break;
        case CARD_SD:    Serial.println("SDSC"); break;
        case CARD_SDHC:  Serial.println("SDHC"); break;
        default:         Serial.println("Unknown"); break;
      }

      Serial.printf("[SD] Card size: %.2f MB\n", SD.cardSize() / (1024.0 * 1024.0));

      // ===== Read stored indices if available (non-fatal if missing) =====
      bool haveIdx  = readUL(indexFile, (unsigned long&)logOffset);
      bool haveFidx = readU16(fileIndexFile, logFileIndex);

      // NEW: If file index is missing/stale, discover highest existing file & treat EOF as authoritative
      if (!haveFidx) {
        uint16_t hi = 0; uint32_t lastSize = 0;
        if (findHighestLogFile(hi, lastSize)) {
          logFileIndex = hi;
          if (!haveIdx) logOffset = lastSize;   // append to EOF if offset unknown
#if DEBUG_FFT_LOGGER
          Serial.printf("[SD] Discovered highest: LOG_%04u.BIN (size %lu)\n",
                        (unsigned)logFileIndex, (unsigned long)lastSize);
#endif
        } else {
          logFileIndex = 0;
          if (!haveIdx) logOffset = 0;         // truly empty card
        }
      } else {
        // We DO have a file index; verify that file actually exists. If not, fall back to discovery.
        uint32_t existingSize = 0;
        if (!getLogFileSizeIfExists(logFileIndex, existingSize)) {
          uint16_t hi = 0; uint32_t lastSize = 0;
          if (findHighestLogFile(hi, lastSize)) {
            logFileIndex = hi;
            if (!haveIdx) logOffset = lastSize;
#if DEBUG_FFT_LOGGER
            Serial.printf("[SD] Index pointed to missing file; using highest existing LOG_%04u.BIN (size %lu)\n",
                          (unsigned)logFileIndex, (unsigned long)lastSize);
#endif
          } else {
            // no files at all; start fresh
            if (!haveIdx) logOffset = 0;
          }
        }
      }

      // ===== Open target log file (creates if missing) =====
      if (!openLogFile()) return false;

      // ===== Reconcile against actual file size (APPEND-SAFE) =====
      uint32_t sz = logFile.size();

      // FIX: never rewind; if indices missing/stale or don't match, APPEND to end
      if (!haveIdx || logOffset != sz) {
        if (logOffset > sz) {
          // stale index beyond EOF -> clamp
          logOffset = sz;
        } else if (logOffset < sz) {
          // index behind file -> append to end
          logOffset = sz;
        } else {
          // equal: fine
        }
      }
      // If file didn't exist before, size==0 and logOffset becomes 0 (fresh file)

      // Seek to reconciled position
      logFile.seek(logOffset);

#if DEBUG_FFT_LOGGER
      {
        char fname[32];
        snprintf(fname, sizeof(fname), "/LOG_%04u.BIN", logFileIndex);
        Serial.printf("[SD] Using log file: %s (size %lu, offset %lu)\n",
                      fname, (unsigned long)sz, (unsigned long)logOffset);
      }
#endif

      // ===== Persist authoritative indices atomically (truncate) =====
      persistIndices();

      loggerStatus = LoggerStatus::OK;
      return true;
    }

    Serial.printf("[SD] Retry %d failed\n", i + 1);
    delay(300);
  }

  Serial.println("[SD] All attempts failed — SD unavailable.");
  loggerStatus = LoggerStatus::SD_INIT_FAILED;
  return false;
}

bool saveFFTFrame(const float* frequencies, const float* magnitudes, size_t count) {
  if (!sdReady || !logFile || !frequencies || !magnitudes || count == 0) {
#if DEBUG_FFT_LOGGER
    Serial.println("[SD] Not ready — skipping FFT save.");
#endif
  logger_fail:
    loggerStatus = LoggerStatus::NOT_READY;
    return false;
  }

  // NEW: BLOCK writes until time is synced & sane (prevents wrong-day timestamps)
  if (!timeIsSane()) {
#if DEBUG_FFT_LOGGER
    Serial.printf("[TIME] Not synced/sane yet (%s) — skipping frame.\n", getFormattedTime().c_str());
#endif
    goto logger_fail;
  }

  const size_t headerSize = 32;
  const size_t dataSize = count * sizeof(float) * 2;
  const size_t rawSize = headerSize + dataSize;
  const size_t alignedSize = ((rawSize + 511) / 512) * 512;

  if (logOffset + alignedSize > MAX_LOG_FILE_SIZE) {
#if DEBUG_FFT_LOGGER
    Serial.println("[SD] Rollover: opening new log file");
#endif
    logFile.close();
    logFileIndex++;
    logOffset = 0;
    if (!openLogFile()) return false;

    // Persist indices immediately so a reboot continues on the new file
    persistIndices();
    logFile.flush();
  }

  if (alignedSize > logBufferSize) {
    Serial.println("[SD] Log buffer too small for frame");
    loggerStatus = LoggerStatus::BUFFER_ALLOC_FAILED;
    return false;
  }

  memset(logBuffer, 0, alignedSize);
  uint8_t* ptr = logBuffer;

  memcpy(ptr, "FFT2", 4);                        ptr += 4;
  uint64_t ts = (uint64_t)time(nullptr);         memcpy(ptr, &ts, sizeof(ts)); ptr += sizeof(ts);
  uint8_t voice = isVoiceDetected() ? 1 : 0;     memcpy(ptr, &voice, sizeof(voice)); ptr += sizeof(voice);
  float snr = getVoiceSNR();                     memcpy(ptr, &snr, sizeof(snr)); ptr += sizeof(snr);
  float energy = getVoiceEnergy();               memcpy(ptr, &energy, sizeof(energy)); ptr += sizeof(energy);
  uint16_t peaks = getVoicePeakCount();          memcpy(ptr, &peaks, sizeof(peaks)); ptr += sizeof(peaks);
  float contrast = getVoiceContrast();           memcpy(ptr, &contrast, sizeof(contrast)); ptr += sizeof(contrast);
  uint16_t bins = count;                         memcpy(ptr, &bins, sizeof(bins)); ptr += sizeof(bins);
  uint8_t reserved[3] = {0};                     memcpy(ptr, reserved, sizeof(reserved)); ptr += sizeof(reserved);

  for (size_t i = 0; i < count; ++i) {
    memcpy(ptr, &frequencies[i], sizeof(float)); ptr += sizeof(float);
    memcpy(ptr, &magnitudes[i], sizeof(float));  ptr += sizeof(float);
  }

  logFile.seek(logOffset);
  uint32_t t0 = millis();
  size_t written = logFile.write(logBuffer, alignedSize);
  uint32_t t1 = millis();

  if (written != alignedSize) {
    Serial.printf("[SD] Write error: %u of %u\n", (unsigned)written, (unsigned)alignedSize);
    loggerStatus = LoggerStatus::WRITE_FAILED;
    return false;
  }

  logOffset += alignedSize;

#if DEBUG_FFT_LOGGER
  if ((t1 - t0) > 100) {
    Serial.printf("[SD] Warning: write took %lu ms\n", t1 - t0);
  }
  Serial.printf("[SD] voice=%d, SNR=%.2f, energy=%.1f, peaks=%u, contrast=%.2f\n",
                voice, snr, energy, peaks, contrast);
  Serial.printf("[SD] Wrote FFT frame (%u bins, %u bytes)\n",
                (unsigned)count, (unsigned)alignedSize);
#endif

  static uint16_t counter = 0;
  if (++counter >= 10) {
    persistIndices();   // FIX: now atomic+truncate
    logFile.flush();
    counter = 0;
  }

  loggerStatus = LoggerStatus::OK;
  return true;
}

bool isLoggerReady() {
  return (loggerStatus == LoggerStatus::OK);
}

LoggerStatus getLoggerStatus() {
  return loggerStatus;
}

bool formatSDCard(bool erase) {
  deinitFFTLogger();

  Serial.println("[SD] Formatting card...");
  SdCardFactory cardFactory;
  SdCard* card = cardFactory.newCard(SdSpiConfig(SD_CS, SHARED_SPI, SD_SCK_MHZ(25)));

  if (!card || card->errorCode()) {
    Serial.println("[SD] Card init failed for formatter.");
    loggerStatus = LoggerStatus::SD_FORMAT_FAILED;
    return false;
  }

  uint32_t sectors = card->sectorCount();
  Serial.printf("[SD] Card size: %.2f GB\n", sectors * 5.12e-7);

  if (erase) {
    const uint32_t ERASE_SIZE = 262144L;
    Serial.println("[SD] Erasing card...");
    uint32_t first = 0, last;
    while (first < sectors) {
      last = std::min(first + ERASE_SIZE - 1, sectors - 1);
      if (!card->erase(first, last)) {
        Serial.println("[SD] Erase failed.");
        loggerStatus = LoggerStatus::SD_FORMAT_FAILED;
        return false;
      }
      Serial.print('.');
      first = last + 1;
    }
    Serial.println("\n[SD] Erase complete.");
  }

  bool ok = false;
  if (sectors > 67108864) {
    ExFatFormatter fmt;
    ok = fmt.format(card, sectorBuffer, &Serial);
    Serial.println("[SD] Formatted as exFAT.");
  } else {
    FatFormatter fmt;
    ok = fmt.format(card, sectorBuffer, &Serial);
    Serial.println("[SD] Formatted as FAT16/32.");
  }

  if (!ok) {
    Serial.println("[SD] Formatting failed.");
    loggerStatus = LoggerStatus::SD_FORMAT_FAILED;
    return false;
  }

  loggerStatus = LoggerStatus::OK;
  Serial.println("[SD] Format successful.");

  return initFFTLogger();
}
