#include "audio_sampler.h"
#include "signal_config.h"

#include <Arduino.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <algorithm>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_adc/adc_continuous.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_heap_caps.h"
#include "esp_adc/adc_filter.h"

static adc_continuous_handle_t adc_handle = nullptr;
static adc_cali_handle_t adc_cali_handle = nullptr;
static adc_iir_filter_handle_t iir_filter = nullptr;

static uint16_t* bufferA = nullptr;
static uint16_t* bufferB = nullptr;
static uint16_t* activeBuffer = nullptr;
static uint16_t* readyBuffer = nullptr;

static volatile uint32_t sampleIndex = 0;
static TaskHandle_t notifyTask = nullptr;

static uint8_t* wavBuffer = nullptr;    // Single pre-allocation for WAV output  (Change #2)
static uint32_t wavBufferSize = 0;

enum class SamplerState {
  IDLE,
  INIT,
  SAMPLING,
  DONE
};

static SamplerState samplerState = SamplerState::IDLE;
static bool samplingComplete = false;

static SamplerStatus samplerStatus = SamplerStatus::NOT_INITIALIZED;

static bool IRAM_ATTR on_conversion_done(adc_continuous_handle_t,
                                         const adc_continuous_evt_data_t*,
                                         void*) {
  BaseType_t mustYield = pdFALSE;
  if (notifyTask) {
    vTaskNotifyGiveFromISR(notifyTask, &mustYield);
  }
  return mustYield == pdTRUE;
}

bool initSampler(TaskHandle_t ownerTask) {
  notifyTask = ownerTask;
  sampleIndex = 0;
  samplerStatus = SamplerStatus::NOT_INITIALIZED;

  Serial.println("[ADC] Allocating PSRAM buffers...");
  bufferA = (uint16_t*)heap_caps_malloc(TOTAL_SAMPLES * sizeof(uint16_t), MALLOC_CAP_SPIRAM);
  bufferB = (uint16_t*)heap_caps_malloc(TOTAL_SAMPLES * sizeof(uint16_t), MALLOC_CAP_SPIRAM);
  if (!bufferA || !bufferB) {
    Serial.println("[ADC] PSRAM buffer allocation failed");
    samplerStatus = SamplerStatus::ALLOC_FAILED;
    return false;
  }

  activeBuffer = bufferA;
  readyBuffer  = bufferB;
  Serial.printf("[ADC] bufferA: %p, bufferB: %p\n", bufferA, bufferB);

  // Pre-allocate WAV buffer for maximum possible size (Change #2)
  wavBufferSize = 44 + (TOTAL_SAMPLES * sizeof(int16_t));
  wavBuffer = (uint8_t*)heap_caps_malloc(wavBufferSize, MALLOC_CAP_SPIRAM);
  if (!wavBuffer) {
    Serial.println("[WAV] Failed to allocate PSRAM WAV buffer");
    samplerStatus = SamplerStatus::ALLOC_FAILED;
    return false;
  }

  adc_continuous_handle_cfg_t handle_cfg = {
    .max_store_buf_size = 4096,
    .conv_frame_size = 1024
  };
  ESP_ERROR_CHECK(adc_continuous_new_handle(&handle_cfg, &adc_handle));

  static adc_digi_pattern_config_t pattern[1];
  pattern[0].atten     = ADC_ATTEN_DB_12;
  pattern[0].channel   = ADC_CHANNEL;
  pattern[0].unit      = ADC_UNIT_1;
  pattern[0].bit_width = SOC_ADC_DIGI_MAX_BITWIDTH;

  adc_continuous_config_t dig_cfg = {};
  dig_cfg.sample_freq_hz = SAMPLE_RATE;
  dig_cfg.conv_mode = ADC_CONV_SINGLE_UNIT_1;
  dig_cfg.format = ADC_DIGI_OUTPUT_FORMAT_TYPE2;
  dig_cfg.adc_pattern = pattern;
  dig_cfg.pattern_num = 1;

  ESP_ERROR_CHECK(adc_continuous_config(adc_handle, &dig_cfg));

  adc_continuous_evt_cbs_t cbs = {
    .on_conv_done = on_conversion_done
  };
  ESP_ERROR_CHECK(adc_continuous_register_event_callbacks(adc_handle, &cbs, nullptr));

#if ENABLE_ADC_IIR_FILTER
  adc_continuous_iir_filter_config_t filter_cfg = {
    .unit = ADC_UNIT_1,
    .channel = ADC_CHANNEL,
    .coeff = ADC_DIGI_IIR_FILTER_COEFF_4
  };
  ESP_ERROR_CHECK(adc_new_continuous_iir_filter(adc_handle, &filter_cfg, &iir_filter));
  ESP_ERROR_CHECK(adc_continuous_iir_filter_enable(iir_filter));
#endif

  // Require calibration to succeed (Change #3)
  adc_cali_curve_fitting_config_t cali_cfg = {
    .unit_id = ADC_UNIT_1,
    .chan = ADC_CHANNEL,
    .atten = ADC_ATTEN_DB_12,
    .bitwidth = ADC_BITWIDTH_12,
  };
  if (adc_cali_create_scheme_curve_fitting(&cali_cfg, &adc_cali_handle) != ESP_OK) {
    Serial.println("[ADC] Calibration failed — system will not start");
    samplerStatus = SamplerStatus::CALIBRATION_FAILED;
    return false;
  }

  samplerStatus = SamplerStatus::OK;
  return true;
}

bool resetSampler() {   // Change #4: Soft reset without reallocation
  if (!adc_handle || !bufferA || !bufferB) return false;
  ESP_ERROR_CHECK(adc_continuous_stop(adc_handle));
  sampleIndex = 0;
  activeBuffer = bufferA;
  readyBuffer = bufferB;
  samplerState = SamplerState::IDLE;
  samplingComplete = false;
  return true;
}

void beginSamplingAsync() {
  samplerState = SamplerState::INIT;
  samplingComplete = false;
}

bool pollSampler() {
  if (!adc_handle) return false;

  static uint8_t dmaBuf[1024];
  static uint32_t bytesRead;
  static uint32_t startMicros = 0;

  if (samplerState == SamplerState::INIT) {
    startMicros = micros();
  }
  if (samplerState == SamplerState::SAMPLING && (micros() - startMicros > 600000)) {
    Serial.println("[ADC] Sampling timeout — forcing soft reset");
    resetSampler();
    return false;
  }

  switch (samplerState) {
    case SamplerState::IDLE:
      return false;

    case SamplerState::INIT:
      sampleIndex = 0;
      ESP_ERROR_CHECK(adc_continuous_start(adc_handle));
      samplerState = SamplerState::SAMPLING;
      break;

    case SamplerState::SAMPLING:
      while (adc_continuous_read(adc_handle, dmaBuf, sizeof(dmaBuf), &bytesRead, 5) == ESP_OK) { // Change #1: keep 5-tick timeout
        auto* data = (adc_digi_output_data_t*)dmaBuf;
        uint32_t count = bytesRead / sizeof(adc_digi_output_data_t);
        for (uint32_t i = 0; i < count && sampleIndex < TOTAL_SAMPLES; ++i) {
          activeBuffer[sampleIndex++] = data[i].type2.data;
          if (i % 64 == 0) vTaskDelay(0); // Change #1: yield inside loop for watchdog safety
        }
        if (sampleIndex >= TOTAL_SAMPLES) {
          ESP_ERROR_CHECK(adc_continuous_stop(adc_handle));
          std::swap(activeBuffer, readyBuffer);
          samplingComplete = true;
          samplerState = SamplerState::DONE;
          break;
        }
      }
      break;

    case SamplerState::DONE:
      samplerState = SamplerState::IDLE;
      return true;
  }
  return false;
}

bool isSamplingDone() { return samplingComplete; }
bool isSamplerActive() { return samplerState == SamplerState::SAMPLING; }
const uint16_t* getReadySamples() { return readyBuffer; }
uint32_t getSampleCount() { return sampleIndex; }
SamplerStatus getSamplerStatus() { return samplerStatus; }

bool convertRawToMV(const uint16_t* raw, float* out_mv, size_t count) {
  if (!adc_cali_handle || !raw || !out_mv) return false;
  for (size_t i = 0; i < count; ++i) {
    int mv = 0;
    adc_cali_raw_to_voltage(adc_cali_handle, raw[i], &mv);
    out_mv[i] = mv;
  }
  return true;
}

const uint8_t* getLastWAV(uint32_t* outSize) {
  if (!readyBuffer || !adc_cali_handle) return nullptr;

  uint32_t numSamples = getSampleCount();
  uint32_t dataSize = numSamples * sizeof(int16_t);
  uint8_t* ptr = wavBuffer;
  memset(ptr, 0, wavBufferSize);

  memcpy(ptr, "RIFF", 4); ptr += 4;
  uint32_t chunkSize = 36 + dataSize;
  memcpy(ptr, &chunkSize, 4); ptr += 4;
  memcpy(ptr, "WAVEfmt ", 8); ptr += 8;
  uint32_t subChunk1Size = 16;
  uint16_t audioFormat = 1;
  uint16_t numChannels = 1;
  uint32_t sampleRate = SAMPLE_RATE;
  uint16_t bitsPerSample = 16;
  uint32_t byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  uint16_t blockAlign = numChannels * (bitsPerSample / 8);
  memcpy(ptr, &subChunk1Size, 4); ptr += 4;
  memcpy(ptr, &audioFormat, 2); ptr += 2;
  memcpy(ptr, &numChannels, 2); ptr += 2;
  memcpy(ptr, &sampleRate, 4); ptr += 4;
  memcpy(ptr, &byteRate, 4); ptr += 4;
  memcpy(ptr, &blockAlign, 2); ptr += 2;
  memcpy(ptr, &bitsPerSample, 2); ptr += 2;
  memcpy(ptr, "data", 4); ptr += 4;
  memcpy(ptr, &dataSize, 4); ptr += 4;

  float* volts = (float*)heap_caps_malloc(numSamples * sizeof(float), MALLOC_CAP_SPIRAM);
  if (!volts) return nullptr;

  convertRawToMV(readyBuffer, volts, numSamples);

  float mean = 0;
  for (uint32_t i = 0; i < numSamples; ++i) {
    volts[i] /= 1000.0f;
    mean += volts[i];
  }
  mean /= numSamples;

  int16_t* pcm = (int16_t*)ptr;
  float peak = 0.0f;
  for (uint32_t i = 0; i < numSamples; ++i) {
    float centered = volts[i] - mean;
    if (fabs(centered) > peak) peak = fabs(centered);
  }
  float gain = (peak > 0) ? (0.95f / peak) : 1.0f; // Change #5: dynamic gain

  for (uint32_t i = 0; i < numSamples; ++i) {
    float centered = (volts[i] - mean) * gain;
    centered = std::clamp(centered, -1.0f, 1.0f);
    pcm[i] = (int16_t)(centered * 32767.0f);
  }

  free(volts);
  if (outSize) *outSize = 44 + dataSize;
  return wavBuffer;
}

void deinitSampler() {
  if (adc_handle) { adc_continuous_deinit(adc_handle); adc_handle = nullptr; }
  if (iir_filter) { adc_continuous_iir_filter_disable(iir_filter); adc_del_continuous_iir_filter(iir_filter); iir_filter = nullptr; }
  if (adc_cali_handle) { adc_cali_delete_scheme_curve_fitting(adc_cali_handle); adc_cali_handle = nullptr; }
  if (bufferA) free(bufferA);
  if (bufferB) free(bufferB);
  if (wavBuffer) free(wavBuffer);
  bufferA = bufferB = activeBuffer = readyBuffer = nullptr;
  wavBuffer = nullptr;
  notifyTask = nullptr;
  sampleIndex = 0;
  samplerState = SamplerState::IDLE;
}


// ALTERNATIVE VERSION USING THE NOTOFICATION THROWN BY SAMPLER DMA ISR INSTEAD OF PERIODIC POLLING

/*
#include "audio_sampler.h"
#include "signal_config.h"

#include <Arduino.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <algorithm>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_adc/adc_continuous.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_heap_caps.h"
#include "esp_adc/adc_filter.h"

static adc_continuous_handle_t adc_handle = nullptr;
static adc_cali_handle_t adc_cali_handle = nullptr;
static adc_iir_filter_handle_t iir_filter = nullptr;

static uint16_t* bufferA = nullptr;
static uint16_t* bufferB = nullptr;
static uint16_t* activeBuffer = nullptr;
static uint16_t* readyBuffer  = nullptr;

static volatile uint32_t sampleIndex = 0;
static TaskHandle_t notifyTask = nullptr;   // task to notify from ISR

static uint8_t*  wavBuffer = nullptr;
static uint32_t  wavBufferSize = 0;

enum class SamplerState { IDLE, INIT, SAMPLING, DONE };
static SamplerState samplerState = SamplerState::IDLE;
static bool samplingComplete = false;

static SamplerStatus samplerStatus = SamplerStatus::NOT_INITIALIZED;

// ---------- ISR: notify sampler task when DMA has data (unchanged) ----------
static bool IRAM_ATTR on_conversion_done(adc_continuous_handle_t,
                                         const adc_continuous_evt_data_t*,
                                         void*) {
  BaseType_t mustYield = pdFALSE;
  if (notifyTask) {
    vTaskNotifyGiveFromISR(notifyTask, &mustYield);
  }
  return mustYield == pdTRUE;
}

bool initSampler(TaskHandle_t ownerTask) {
  notifyTask = ownerTask;              // EVENT-DRIVEN: store the sampler task handle
  sampleIndex = 0;
  samplerStatus = SamplerStatus::NOT_INITIALIZED;

  Serial.println("[ADC] Allocating PSRAM buffers...");
  bufferA = (uint16_t*)heap_caps_malloc(TOTAL_SAMPLES * sizeof(uint16_t), MALLOC_CAP_SPIRAM);
  bufferB = (uint16_t*)heap_caps_malloc(TOTAL_SAMPLES * sizeof(uint16_t), MALLOC_CAP_SPIRAM);
  if (!bufferA || !bufferB) {
    Serial.println("[ADC] PSRAM buffer allocation failed");
    samplerStatus = SamplerStatus::ALLOC_FAILED;
    return false;
  }

  activeBuffer = bufferA;
  readyBuffer  = bufferB;
  Serial.printf("[ADC] bufferA: %p, bufferB: %p\n", bufferA, bufferB);

  // Pre-allocate WAV buffer
  wavBufferSize = 44 + (TOTAL_SAMPLES * sizeof(int16_t));
  wavBuffer = (uint8_t*)heap_caps_malloc(wavBufferSize, MALLOC_CAP_SPIRAM);
  if (!wavBuffer) {
    Serial.println("[WAV] Failed to allocate PSRAM WAV buffer");
    samplerStatus = SamplerStatus::ALLOC_FAILED;
    return false;
  }

  adc_continuous_handle_cfg_t handle_cfg = {
    .max_store_buf_size = 4096,
    .conv_frame_size    = 1024
  };
  ESP_ERROR_CHECK(adc_continuous_new_handle(&handle_cfg, &adc_handle));

  static adc_digi_pattern_config_t pattern[1];
  pattern[0].atten     = ADC_ATTEN_DB_12;
  pattern[0].channel   = ADC_CHANNEL;
  pattern[0].unit      = ADC_UNIT_1;
  pattern[0].bit_width = SOC_ADC_DIGI_MAX_BITWIDTH;

  adc_continuous_config_t dig_cfg = {};
  dig_cfg.sample_freq_hz = SAMPLE_RATE;
  dig_cfg.conv_mode      = ADC_CONV_SINGLE_UNIT_1;
  dig_cfg.format         = ADC_DIGI_OUTPUT_FORMAT_TYPE2;
  dig_cfg.adc_pattern    = pattern;
  dig_cfg.pattern_num    = 1;

  ESP_ERROR_CHECK(adc_continuous_config(adc_handle, &dig_cfg));

  // Register ISR callback (used now)
  adc_continuous_evt_cbs_t cbs = { .on_conv_done = on_conversion_done };
  ESP_ERROR_CHECK(adc_continuous_register_event_callbacks(adc_handle, &cbs, nullptr));

#if ENABLE_ADC_IIR_FILTER
  adc_continuous_iir_filter_config_t filter_cfg = {
    .unit    = ADC_UNIT_1,
    .channel = ADC_CHANNEL,
    .coeff   = ADC_DIGI_IIR_FILTER_COEFF_4
  };
  ESP_ERROR_CHECK(adc_new_continuous_iir_filter(adc_handle, &filter_cfg, &iir_filter));
  ESP_ERROR_CHECK(adc_continuous_iir_filter_enable(iir_filter));
#endif

  // Require calibration to succeed
  adc_cali_curve_fitting_config_t cali_cfg = {
    .unit_id  = ADC_UNIT_1,
    .chan     = ADC_CHANNEL,
    .atten    = ADC_ATTEN_DB_12,
    .bitwidth = ADC_BITWIDTH_12,
  };
  if (adc_cali_create_scheme_curve_fitting(&cali_cfg, &adc_cali_handle) != ESP_OK) {
    Serial.println("[ADC] Calibration failed — system will not start");
    samplerStatus = SamplerStatus::CALIBRATION_FAILED;
    return false;
  }

  samplerStatus = SamplerStatus::OK;
  return true;
}

bool resetSampler() {
  if (!adc_handle || !bufferA || !bufferB) return false;
  ESP_ERROR_CHECK(adc_continuous_stop(adc_handle));
  sampleIndex   = 0;
  activeBuffer  = bufferA;
  readyBuffer   = bufferB;
  samplerState  = SamplerState::IDLE;
  samplingComplete = false;
  return true;
}

void beginSamplingAsync() {
  samplerState = SamplerState::INIT;
  samplingComplete = false;
}

bool pollSampler() {
  if (!adc_handle) return false;

  static uint8_t  dmaBuf[1024];
  static uint32_t bytesRead;
  static uint32_t startMicros = 0;

  if (samplerState == SamplerState::INIT) {
    startMicros = micros();
  }
  if (samplerState == SamplerState::SAMPLING && (micros() - startMicros > 600000)) {
    Serial.println("[ADC] Sampling timeout — forcing soft reset");
    resetSampler();
    return false;
  }

  switch (samplerState) {
    case SamplerState::IDLE:
      return false;

    case SamplerState::INIT:
      sampleIndex = 0;
      ESP_ERROR_CHECK(adc_continuous_start(adc_handle));

      // EVENT-DRIVEN: clear any stale notifications before starting
      (void)ulTaskNotifyTake(pdTRUE, 0);

      samplerState = SamplerState::SAMPLING;
      break;

    case SamplerState::SAMPLING: {
      // EVENT-DRIVEN: wait for ISR to notify that DMA has data
      // short timeout keeps our 600 ms guard effective
      if (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(20)) == 0) {
        // No notify this tick; nothing to read yet
        return false;
      }

      // Drain all currently available DMA data (non-blocking reads)
      while (adc_continuous_read(adc_handle, dmaBuf, sizeof(dmaBuf), &bytesRead, 0) == ESP_OK) {
        auto* data  = (adc_digi_output_data_t*)dmaBuf;
        uint32_t cnt = bytesRead / sizeof(adc_digi_output_data_t);
        for (uint32_t i = 0; i < cnt && sampleIndex < TOTAL_SAMPLES; ++i) {
          activeBuffer[sampleIndex++] = data[i].type2.data;
          if ((i & 63) == 0) vTaskDelay(0); // watchdog-friendly yield
        }
        if (sampleIndex >= TOTAL_SAMPLES) {
          ESP_ERROR_CHECK(adc_continuous_stop(adc_handle));
          std::swap(activeBuffer, readyBuffer);
          samplingComplete = true;
          samplerState = SamplerState::DONE;
          break;
        }
      }
      break;
    }

    case SamplerState::DONE:
      samplerState = SamplerState::IDLE;
      return true;
  }
  return false;
}

bool isSamplingDone()           { return samplingComplete; }
bool isSamplerActive()          { return samplerState == SamplerState::SAMPLING; }
const uint16_t* getReadySamples(){ return readyBuffer; }
uint32_t getSampleCount()       { return sampleIndex; }
SamplerStatus getSamplerStatus(){ return samplerStatus; }

bool convertRawToMV(const uint16_t* raw, float* out_mv, size_t count) {
  if (!adc_cali_handle || !raw || !out_mv) return false;
  for (size_t i = 0; i < count; ++i) {
    int mv = 0;
    adc_cali_raw_to_voltage(adc_cali_handle, raw[i], &mv);
    out_mv[i] = mv;
  }
  return true;
}

const uint8_t* getLastWAV(uint32_t* outSize) {
  if (!readyBuffer || !adc_cali_handle) return nullptr;

  uint32_t numSamples = getSampleCount();
  uint32_t dataSize   = numSamples * sizeof(int16_t);
  uint8_t* ptr = wavBuffer;
  memset(ptr, 0, wavBufferSize);

  memcpy(ptr, "RIFF", 4); ptr += 4;
  uint32_t chunkSize = 36 + dataSize;
  memcpy(ptr, &chunkSize, 4); ptr += 4;
  memcpy(ptr, "WAVEfmt ", 8); ptr += 8;
  uint32_t subChunk1Size = 16;
  uint16_t audioFormat   = 1;
  uint16_t numChannels   = 1;
  uint32_t sampleRate    = SAMPLE_RATE;
  uint16_t bitsPerSample = 16;
  uint32_t byteRate      = sampleRate * numChannels * (bitsPerSample / 8);
  uint16_t blockAlign    = numChannels * (bitsPerSample / 8);
  memcpy(ptr, &subChunk1Size, 4); ptr += 4;
  memcpy(ptr, &audioFormat, 2);   ptr += 2;
  memcpy(ptr, &numChannels, 2);   ptr += 2;
  memcpy(ptr, &sampleRate, 4);    ptr += 4;
  memcpy(ptr, &byteRate, 4);      ptr += 4;
  memcpy(ptr, &blockAlign, 2);    ptr += 2;
  memcpy(ptr, &bitsPerSample, 2); ptr += 2;
  memcpy(ptr, "data", 4);         ptr += 4;
  memcpy(ptr, &dataSize, 4);      ptr += 4;

  float* volts = (float*)heap_caps_malloc(numSamples * sizeof(float), MALLOC_CAP_SPIRAM);
  if (!volts) return nullptr;

  convertRawToMV(readyBuffer, volts, numSamples);

  float mean = 0;
  for (uint32_t i = 0; i < numSamples; ++i) {
    volts[i] /= 1000.0f;
    mean += volts[i];
  }
  mean /= numSamples;

  int16_t* pcm = (int16_t*)ptr;
  float peak = 0.0f;
  for (uint32_t i = 0; i < numSamples; ++i) {
    float centered = volts[i] - mean;
    if (fabs(centered) > peak) peak = fabs(centered);
  }
  float gain = (peak > 0) ? (0.95f / peak) : 1.0f;

  for (uint32_t i = 0; i < numSamples; ++i) {
    float centered = (volts[i] - mean) * gain;
    centered = std::clamp(centered, -1.0f, 1.0f);
    pcm[i] = (int16_t)(centered * 32767.0f);
  }

  free(volts);
  if (outSize) *outSize = 44 + dataSize;
  return wavBuffer;
}

void deinitSampler() {
  if (adc_handle)      { adc_continuous_deinit(adc_handle); adc_handle = nullptr; }
  if (iir_filter)      { adc_continuous_iir_filter_disable(iir_filter); adc_del_continuous_iir_filter(iir_filter); iir_filter = nullptr; }
  if (adc_cali_handle) { adc_cali_delete_scheme_curve_fitting(adc_cali_handle); adc_cali_handle = nullptr; }
  if (bufferA) free(bufferA);
  if (bufferB) free(bufferB);
  if (wavBuffer) free(wavBuffer);
  bufferA = bufferB = activeBuffer = readyBuffer = nullptr;
  wavBuffer = nullptr;
  notifyTask = nullptr;
  sampleIndex = 0;
  samplerState = SamplerState::IDLE;
}

*/