#pragma once

#include <Arduino.h>
#include <stdint.h>

// === Enable optional ADC filtering ===
#define ENABLE_ADC_IIR_FILTER true

// === Optional compile-time debug ===
#define DEBUG_ADC_SAMPLES false

// === Status codes ===
enum class SamplerStatus {
  OK,
  NOT_INITIALIZED,
  ALLOC_FAILED,
  CALIBRATION_FAILED
};

// === Lifecycle ===
bool initSampler(TaskHandle_t ownerTask);       // Full initialization + allocations
void deinitSampler();                           // Free resources
bool resetSampler();                            // ✅ NEW: Soft reset without realloc

// === Sampling control ===
void beginSamplingAsync();                      // Start FSM
bool pollSampler();                             
bool isSamplingDone();                          
bool isSamplerActive();                         

// === Sample access ===
const uint16_t* getReadySamples();              
uint16_t getRawSample(uint32_t index);          
int getSampleVoltage(uint32_t index);           
uint32_t getSampleCount();                      

// === WAV output ===
const uint8_t* getLastWAV(uint32_t* outSize);   

// === Optional conversion helper ===
bool convertRawToMV(const uint16_t* raw, float* out_mv, size_t count);  

// === Status query ===
SamplerStatus getSamplerStatus();
