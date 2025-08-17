#include "fft_engine.h"
#include "arduinoFFT.h"
#include "signal_config.h"
#include <math.h>
#include <string.h>
#include <algorithm>
#include "esp_heap_caps.h"

// === Config (existing) ===
#define VOICE_MIN_HZ 100
#define VOICE_MAX_HZ 4000
#define SNR_THRESHOLD 1.6f
#define DELTA_E_THRESHOLD 10.0f
#define PEAK_COUNT_THRESHOLD 3
#define CONTRAST_THRESHOLD 3.0f

// === New minimal config for robust presence + intensity ===
#define SNR_MIN_LINEAR        1.6f     // ≈ +2.0 dB
#define SFM_MAX_FOR_VOICE     0.55f    // <~0.55 → harmonic/voiced; >=~0.55 → noise-ish
#define RISE_DB_OVER_BASE     3.0f     // ≥3 dB above recent baseline
#define BASELINE_ALPHA        0.05f    // EMA speed for baseline when no voice
#define EPS                   1e-9f

// === Internal Buffers in PSRAM ===
static float* vReal = nullptr;
static float* vImag = nullptr;
static float* magnitudes = nullptr;
static float* frequencies = nullptr;

static ArduinoFFT<float>* FFT = nullptr;

// === Voice Detection State (existing) ===
static volatile bool fftReady = false;
static FFTStatus fftStatus = FFTStatus::NOT_READY;

static size_t minVoiceBin = 0;
static size_t maxVoiceBin = 0;

static bool voiceDetected = false;
static float voiceEnergy = 0.0f;
static float noiseEnergy = 0.0f;
static float snr = 0.0f;           // exported SNR (now RMS-based, more stable)
static int   peakCount = 0;
static float contrast = 0.0f;
static float prevVoiceEnergy = 0.0f;

// === New internal features (no API break) ===
static float sfm = 1.0f;               // spectral flatness in voice band
static float bandRMS = 0.0f;           // RMS magnitude in voice band
static float noiseRMS = 0.0f;          // RMS magnitude outside band
static float baselineBandRMS = 0.0f;   // EMA baseline of bandRMS (updated when no-voice)
static float voiceIntensityDB = 0.0f;  // dB above baseline
static uint8_t confirmCnt = 0;         // 2-frame confirmation
static bool voiceState = false;        // debounced presence

bool initFFTEngine() {
  // Allocate all buffers in PSRAM, free on failure
  vReal       = (float*)heap_caps_malloc(sizeof(float) * FFT_SIZE, MALLOC_CAP_SPIRAM);
  vImag       = (float*)heap_caps_malloc(sizeof(float) * FFT_SIZE, MALLOC_CAP_SPIRAM);
  magnitudes  = (float*)heap_caps_malloc(sizeof(float) * FFT_BINS, MALLOC_CAP_SPIRAM);
  frequencies = (float*)heap_caps_malloc(sizeof(float) * FFT_BINS, MALLOC_CAP_SPIRAM);

  if (!vReal || !vImag || !magnitudes || !frequencies) {
    Serial.println("[FFT] Failed to allocate FFT buffers");
    deinitFFTEngine();
    return false;
  }

  FFT = new ArduinoFFT<float>(vReal, vImag, (float)FFT_SIZE, (float)SAMPLE_RATE);
  if (!FFT) {
    Serial.println("[FFT] Failed to instantiate FFT object");
    deinitFFTEngine();
    return false;
  }

  for (size_t i = 0; i < FFT_BINS; ++i) {
    frequencies[i] = ((float)i * SAMPLE_RATE) / FFT_SIZE;
  }

  minVoiceBin = (size_t)((VOICE_MIN_HZ * FFT_SIZE) / SAMPLE_RATE);
  maxVoiceBin = (size_t)((VOICE_MAX_HZ * FFT_SIZE) / SAMPLE_RATE);
  if (maxVoiceBin >= FFT_BINS) maxVoiceBin = FFT_BINS - 1;

  Serial.printf("[FFT] Engine initialized — %d bins, VOICE bins: %u–%u\n",
                FFT_BINS, (unsigned)minVoiceBin, (unsigned)maxVoiceBin);
  return true;
}

void resetFFTEngine() {
  fftReady = false;
  fftStatus = FFTStatus::NOT_READY;
  voiceDetected = false;
  voiceEnergy = noiseEnergy = snr = contrast = 0.0f;
  peakCount = 0;
  prevVoiceEnergy = 0.0f;

  // New state
  sfm = 1.0f;
  bandRMS = noiseRMS = 0.0f;
  // Preserve baseline so it survives across frames; reset confirmation only
  confirmCnt = 0;
  voiceState = false;
  voiceIntensityDB = 0.0f;
}

bool processFFT(const float* mvSamples, size_t count) {
  if (!mvSamples) {
    fftStatus = FFTStatus::NULL_INPUT;
    return false;
  }
  if (count < FFT_SIZE) {
    fftStatus = FFTStatus::TOO_FEW_SAMPLES;
    return false;
  }

  memset(magnitudes, 0, sizeof(float) * FFT_BINS);
  fftStatus = FFTStatus::OK;
  size_t numFFTs = 0;

  const size_t step = FFT_STEP_SIZE;
  for (size_t offset = 0; offset + FFT_SIZE <= count; offset += step) {
    float mean = 0.0f;
    for (size_t i = 0; i < FFT_SIZE; ++i) {
      vReal[i] = mvSamples[offset + i] / MV_TO_V_SCALE;  // convert mV → V
      vImag[i] = 0.0f;
      mean += vReal[i];
    }

    mean /= FFT_SIZE;
    for (size_t i = 0; i < FFT_SIZE; ++i) {
      vReal[i] -= mean; // DC removal
    }

    FFT->windowing(FFTWindow::Hamming, FFTDirection::Forward);
    FFT->compute(FFTDirection::Forward);
    FFT->complexToMagnitude();

    // Pool magnitudes: max in voice band, average out-of-band
    for (size_t i = 0; i < FFT_BINS; ++i) {
      float mag = vReal[i];
      if (i >= minVoiceBin && i <= maxVoiceBin) {
        if (mag < MAGNITUDE_THRESHOLD) mag = 0.0f; // in-band gate
        magnitudes[i] = fmaxf(magnitudes[i], mag); // max pooling in voice band
      } else {
        magnitudes[i] += mag; // accumulate for averaging later
      }
    }

    numFFTs++;
    if ((offset & (step * 4 - 1)) == 0) vTaskDelay(0); // periodic yield (WDT-safe)
  }

  // Average out-of-band magnitudes
  for (size_t i = 0; i < FFT_BINS; ++i) {
    if (i < minVoiceBin || i > maxVoiceBin) {
      magnitudes[i] /= (float)numFFTs;
    }
  }

  // === Feature extraction (existing + new) ===
  voiceEnergy = noiseEnergy = 0.0f;
  peakCount = 0;
  float maxVoice = 0.0f;
  float meanVoice = 0.0f;

  for (size_t i = 0; i < FFT_BINS; ++i) {
    float mag = magnitudes[i];
    if (i >= minVoiceBin && i <= maxVoiceBin) {
      voiceEnergy += mag * mag;
      meanVoice += mag;
      if (mag > maxVoice) maxVoice = mag;
    } else {
      noiseEnergy += mag * mag;
    }
  }
  meanVoice /= (maxVoiceBin - minVoiceBin + 1);

  // Contrast + peaks kept for backward compatibility/logging
  contrast = (meanVoice > 0.0f) ? (maxVoice / meanVoice) : 0.0f;
  for (size_t i = minVoiceBin; i <= maxVoiceBin; ++i) {
    if (magnitudes[i] > meanVoice * 1.5f) {
      peakCount++;
    }
  }

  // New: RMS in/out band + spectral flatness in band
  bandRMS = 0.0f;
  noiseRMS = 0.0f;
  float bandSum = 0.0f;
  float logSum  = 0.0f;
  size_t bandBins  = (maxVoiceBin - minVoiceBin + 1);
  size_t noiseBins = 0;

  for (size_t i = 0; i < FFT_BINS; ++i) {
    float m = magnitudes[i];
    if (i >= minVoiceBin && i <= maxVoiceBin) {
      bandRMS += m * m;
      bandSum += m;
      logSum  += logf(m + EPS);
    } else {
      noiseRMS += m * m;
      noiseBins++;
    }
  }
  bandRMS  = sqrtf(bandRMS / (float)bandBins);
  noiseRMS = (noiseBins > 0) ? sqrtf(noiseRMS / (float)noiseBins) : 0.0f;

  float amean = bandSum / (float)bandBins;
  float gmean = expf(logSum / (float)bandBins);
  sfm = gmean / (amean + EPS); // 0 = peaky (voiced), 1 = flat (noise)

  // Update adaptive baseline only when not currently in voice state
  if (!voiceState) {
    if (baselineBandRMS <= 0.0f) baselineBandRMS = bandRMS; // initialize
    baselineBandRMS = (1.0f - BASELINE_ALPHA) * baselineBandRMS + BASELINE_ALPHA * bandRMS;
  }

  // Stable SNR (exported)
  float snr_lin = (noiseRMS > 0.0f) ? ((bandRMS * bandRMS) / (noiseRMS * noiseRMS + EPS)) : 0.0f;
  snr = snr_lin;

  // dB rise over adaptive baseline → intensity
  float riseDB = 20.0f * log10f((bandRMS + EPS) / (baselineBandRMS + EPS));
  voiceIntensityDB = (riseDB > 0.0f) ? riseDB : 0.0f;

  // Optional: retain deltaE for debug (not used in final decision)
  float deltaE = fabsf(voiceEnergy - prevVoiceEnergy);
  prevVoiceEnergy = voiceEnergy;

  // === Minimal robust decision ===
  bool passesCore = (snr_lin >= SNR_MIN_LINEAR) && (sfm <= SFM_MAX_FOR_VOICE) && (riseDB >= RISE_DB_OVER_BASE);

  // Two-frame confirmation & hysteresis via confirmCnt
  if (passesCore) {
    confirmCnt = (confirmCnt < 2) ? (confirmCnt + 1) : 2;
  } else {
    confirmCnt = (confirmCnt > 0) ? (confirmCnt - 1) : 0;
  }
  voiceState = (confirmCnt >= 2);

  // Exported flag (backward-compatible)
  voiceDetected = voiceState;

#if DEBUG_FFT_VALUES
  Serial.printf("[FFT] SNR=%.2f | SFM=%.2f | rise=%.1f dB | ΔE=%.1f | peaks=%d | contrast=%.2f → voice: %s\n",
    snr, sfm, riseDB, deltaE, peakCount, contrast, voiceDetected ? "YES" : "no");
#endif

  fftReady = true;
  return true;
}

bool isFFTReady()          { return fftReady; }
void resetFFTReady()       { fftReady = false; }
FFTStatus getFFTStatus()   { return fftStatus; }

bool isVoiceDetected()     { return voiceDetected; }
float getVoiceSNR()        { return snr; }
float getVoiceEnergy()     { return voiceEnergy; }
int   getVoicePeakCount()  { return peakCount; }
float getVoiceContrast()   { return contrast; }

const float* getFFTMagnitudes()  { return magnitudes; }
const float* getFFTFrequencies() { return frequencies; }
size_t getFFTBins()              { return FFT_BINS; }

float getDominantFrequency(float& magnitudeOut) {
  magnitudeOut = 0.0f;
  if (!magnitudes || !frequencies || FFT_BINS == 0) return 0.0f;

  size_t peakIdx = 0;
  float peak = 0.0f;
  for (size_t i = 0; i < FFT_BINS; i++) {
    if (magnitudes[i] > peak) {
      peak = magnitudes[i];
      peakIdx = i;
    }
  }
  magnitudeOut = peak;
  return frequencies[peakIdx];
}

// === Optional new getters (add to fft_engine.h only if you plan to use them) ===
float getVoiceIntensityDB() { return voiceIntensityDB; }
// 0–100 scale mapped from 0–20 dB
float getVoiceIntensityPct() {
  float pct = (voiceIntensityDB / 20.0f) * 100.0f;
  if (pct < 0.0f) pct = 0.0f;
  if (pct > 100.0f) pct = 100.0f;
  return pct;
}

void deinitFFTEngine() {
  resetFFTEngine();
  if (vReal)       { free(vReal); vReal = nullptr; }
  if (vImag)       { free(vImag); vImag = nullptr; }
  if (magnitudes)  { free(magnitudes); magnitudes = nullptr; }
  if (frequencies) { free(frequencies); frequencies = nullptr; }
  if (FFT)         { delete FFT; FFT = nullptr; }
}
