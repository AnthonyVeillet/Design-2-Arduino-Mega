#include <Arduino.h>
#include "sampler.h"
#include "PWM.h"

const int ledPin = 13; // LED intégrée

uint16_t lastPositionVal = 0;
uint16_t positionVal = 0;

uint16_t lastCourantVal = 0;
uint16_t courantVal = 0;

void setup()
{
  Serial.begin(1000000);
  pinMode(ledPin, OUTPUT); // LED

  cli(); // désactiver interruptions
  setup_ADC();
  setup_PWM();
  sei(); // réactiver interruptions
}

void loop()
{
  positionVal = adcValues[ADC_POSITION_A0];
  courantVal = adcValues[ADC_COURANT_A1];

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
      Serial.write('K'); // ACK stop
    }
  }

  if (acquisitionActive)
  {
    sendData = false;

    uint16_t a0 = adcValues[0];
    uint16_t a1 = adcValues[1];

    Serial.write((uint8_t *)&a0, 2);
    Serial.write((uint8_t *)&a1, 2);
  }

  if (lastPositionVal != positionVal)
  {
    lastPositionVal = positionVal;
  }

  if (lastCourantVal != courantVal)
  {
    lastCourantVal = courantVal;
  }
}
