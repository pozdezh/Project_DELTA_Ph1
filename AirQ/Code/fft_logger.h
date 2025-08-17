#pragma once
#include <Arduino.h>

enum class LoggerStatus {
  NOT_READY,
  OK,
  SD_INIT_FAILED,
  FILE_OPEN_FAILED,
  BUFFER_ALLOC_FAILED,
  WRITE_FAILED,
  SD_FORMAT_FAILED
};

// === Setup & Teardown ===
bool initFFTLogger();
void deinitFFTLogger();
bool recoverFFTLogger();

// === Runtime Logging ===
bool saveFFTFrame(const float* frequencies, const float* magnitudes, size_t count);

// === Runtime Status ===
LoggerStatus getLoggerStatus();
bool isLoggerReady();

// === Maintenance ===
bool formatSDCard(bool erase = false);


