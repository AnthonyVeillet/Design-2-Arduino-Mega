#include "PWM.h"
#include "Arduino.h"

void setup_Timer2() {
  // Timer 2 (pour PWM)
  TCCR2A = 0;
  TCCR2B = 0;
  TCCR2A = (1 << WGM20) | (1 << WGM21) | (1 << COM2A1);  // Fast PWM 8-bit non-inverseur

  // Prescaler = 1 → compteur compte à 16 MHz
  TCCR2B = (1 << CS20);  // CS22:0 = 001 → prescaler 1

  // Valeur PWM initiale (0–255)
  OCR2A = 127;  // 50% duty cycle
}

void setNewDutyCycleValue(uint8_t dutyCycle) {
  if (dutyCycle > 100) {
    return;
  }
  uint8_t count = (dutyCycle * 255) / 100;
  OCR2A = count;
}