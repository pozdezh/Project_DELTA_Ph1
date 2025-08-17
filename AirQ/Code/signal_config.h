#pragma once

// ==== AUDIO SAMPLING ====
#define SAMPLE_RATE     44100              // 44.1 kHz audio sampling
#define RECORD_MS       500                // 500 ms recording
#define TOTAL_SAMPLES   ((SAMPLE_RATE * RECORD_MS) / 1000)
#define ADC_CHANNEL     ADC_CHANNEL_7      // Your actual ADC channel (e.g., GPIO8)

// ==== FFT ====
#define FFT_SIZE 4096
#define FFT_STEP_SIZE 2048  // keep 50% overlap
#define FFT_BINS        (FFT_SIZE / 2)
#define MAGNITUDE_THRESHOLD  0.010f        // Minimum valid magnitude (suppress noise)
#define MV_TO_V_SCALE   1000.0f

// ==== SD CARD PINS (SPI) ====
#define SD_CS    12
#define SD_SCK   36
#define SD_MISO  37
#define SD_MOSI  35

// ==== BUTTON AND TFT ====
#define BUTTON_PIN 6
#define BACKLIGHT_PIN 13
#define TFT_CS 9
#define TFT_DC 11
#define TFT_RST 10
#define STEMMA_PIN 7
