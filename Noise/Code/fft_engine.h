#pragma once

#include <Arduino.h>
#include <stdint.h>

// === Optional compile-time debug ===
#define DEBUG_FFT_VALUES false

// === FFT status codes ===
enum class FFTStatus {
  OK,
  NOT_READY,
  NULL_INPUT,
  TOO_FEW_SAMPLES
};

// === Lifecycle ===
bool initFFTEngine();       // Full initialization + PSRAM allocations
void deinitFFTEngine();     // Free all resources
void resetFFTEngine();      // ✅ Soft reset without realloc

// === Processing ===
bool processFFT(const float* mvSamples, size_t count);

// === State ===
bool isFFTReady();
void resetFFTReady();
FFTStatus getFFTStatus();

// === Voice detection results ===
bool isVoiceDetected();
float getVoiceSNR();
float getVoiceEnergy();
int getVoicePeakCount();
float getVoiceContrast();

// === Spectrum access ===
const float* getFFTMagnitudes();
const float* getFFTFrequencies();
size_t getFFTBins();

// === Utility ===
float getDominantFrequency(float& magnitudeOut);
float getVoiceIntensityDB();
float getVoiceIntensityPct();
