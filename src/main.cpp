#include <Arduino.h>
#include "sampler.h"
#include "PWM.h"
#include "asservissement.h"

const int ledPin = 13; // LED intégrée

uint16_t positionVal = 0;
uint16_t courantVal = 0;

void setup()
{
  Serial.begin(115200);
  pinMode(ledPin, OUTPUT); // LED

  cli(); // désactiver interruptions
  setup_ADC();
  setup_PWM();
  sei(); // réactiver interruptions

  delay(10); // Laisser temps à l'ADC pour première acquisition
  tare();

  setupTimerPID();
}

uint16_t toggleCounter = 0;

void loop()
{

  if (Serial.available())
  {
    char cmd = Serial.read();
    if (cmd == 'S')
    {
      acquisitionActive = true;
      Serial.write('O'); // envoie ACK
    }
    else if (cmd == 'E')
    {
      acquisitionActive = false;
      // Serial.write('K'); // ACK stop
    }
    else if (cmd == 'I') // mode identification ON
    {
      modeIdentification = true;
    }
    else if (cmd == 'N') // mode normal
    {
      resetPID();
      modeIdentification = false;
    }
    else if (cmd == 'P')
    {
      while (Serial.available() < 1)
        ;
      uint8_t pwm = Serial.read(); // 0–100

      setNewDutyCycleValue(pwm / 100.0f);
    }
  }

  // Envoi du courant en continu quand la position est asservie pour afficher la masse.
  uint16_t courant = 0;
  if (toggleCounter % 20 == 0)
  {
    Serial.write('M');
    Serial.write((uint8_t *)&courant, 2);
    Serial.write(mesureValide ? 1 : 0);
  }

  if (acquisitionActive)
  {
    cli();
    uint16_t a0 = adcValues[0];
    uint16_t a1 = adcValues[1];
    sei();

    if (toggleCounter % 10 == 0)
    {
      Serial.write('D');
      Serial.write((uint8_t *)&a0, 2);
      Serial.write((uint8_t *)&a1, 2);
    }
  }

  toggleCounter++;
  if (toggleCounter >= 5000)
  {
    digitalWrite(13, !digitalRead(13));
    toggleCounter = 0;
  }
}
