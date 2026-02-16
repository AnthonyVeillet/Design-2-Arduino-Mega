#include "PWM.h"
#include "Arduino.h"

void setup_PWM()
{
  pinMode(5, OUTPUT);

  // Reset Timer3
  TCCR3A = 0;
  TCCR3B = 0;
  TCNT3  = 0;

  // Fast PWM avec ICR3 comme TOP (10 bits)
  ICR3 = 1023;        // TOP = 1023 → résolution 10 bits
  OCR3A = 511;  // duty cycle initial 50%

  // Mode Fast PWM non-inverting pour OC3A
  TCCR3A = (1 << WGM31) | (1 << COM3A1);
  TCCR3B = (1 << WGM33) | (1 << WGM32) | (1 << CS30); // prescaler = 1 → fPWM ≈ 15.625 kHz
}

void setNewDutyCycleValue(uint8_t dutyCycle)
{
  if (dutyCycle > 100)
  {
    return;
  }
  uint16_t count = (dutyCycle * 1023) / 100;
  OCR1B = count;
}