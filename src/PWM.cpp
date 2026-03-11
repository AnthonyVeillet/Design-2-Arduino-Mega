#include "PWM.h"
#include "Arduino.h"

void setup_PWM()
{
  pinMode(5, OUTPUT);

  // Reset Timer3
  TCCR3A = 0;
  TCCR3B = 0;
  TCNT3 = 0;

  // Fast PWM avec ICR3 comme TOP (10 bits)
  ICR3 = 1023; // TOP = 1023 → résolution 10 bits
  OCR3A = 0; // duty cycle initial 0%

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
  OCR3A = count;
}

void testResolutionPWM()
{
  OCR3A = 510;
  delay(100);
  OCR3A = 511;
  delay(100);
}

float Kpwm = 1023.0;   // gain conversion commande → PWM
#define PWM_MAX 1023
#define PWM_MIN 0 
uint16_t convertCommandePWM(float commande)
{
    int pwm = Kpwm * commande;

    if (pwm > PWM_MAX) pwm = PWM_MAX;
    if (pwm < PWM_MIN) pwm = PWM_MIN;

    return pwm;
}