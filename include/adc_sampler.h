#pragma once
#include <Arduino.h>
#include <stdint.h>

struct Sample16 {
  uint16_t adc;   // 0..1023
};

class ADCSampler {
public:
  static void begin(uint32_t fs_hz, uint8_t adc_pin);
  static void stop();

  static bool available();
  static Sample16 read();

  static uint32_t dropped();

private:
  static void setupTimer1(uint32_t fs_hz);
  static void setupADC(uint8_t adc_pin);
};
