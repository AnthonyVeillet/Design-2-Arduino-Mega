#include <Arduino.h>
#include "sampler_ident.h"
#include "PWM.h"

const int ledPin = 13; // LED intégrée

void setup()
{
  Serial.begin(1000000);
  pinMode(ledPin, OUTPUT);

  cli(); // désactiver interruptions
  setup_ADC();
  setup_PWM();
  sei(); // réactiver interruptions

  // Sécurité : on force le PWM à 0 au démarrage
  setNewDutyCycleValue(50);

  acquisitionActive = false;
  sendData = false;
}

void loop()
{
  // Gestion des commandes série
  while (Serial.available())
  {
    char cmd = Serial.read();

    if (cmd == 'S')
    {
      cli();
      decimationCounter = 0;
      acquisitionActive = true;
      sendData = false;
      sei();

      Serial.write('O'); // ACK start
    }
    else if (cmd == 'E')
    {
      cli();
      acquisitionActive = false;
      sendData = false;
      decimationCounter = 0;
      sei();

      Serial.write('K'); // ACK stop
    }
    else if (cmd == 'P')
    {
      // Attend un octet supplémentaire contenant le duty 0..100
      if (Serial.available() > 0)
      {
        uint8_t pwmValue = (uint8_t)Serial.read();

        if (pwmValue > 100)
          pwmValue = 100;

        setNewDutyCycleValue(pwmValue);
        // Retirer car risque de décaller les données
        //Serial.write('D'); // ACK duty
      }
      else
      {
        // Pas encore l'octet du PWM, on ressort de la boucle
        break;
      }
    }
  }

  // Envoi seulement quand une nouvelle donnée décimée est prête
  if (acquisitionActive && sendData)
  {
    uint16_t a0 = 0;
    uint16_t a1 = 0;

    cli();
    a0 = positionReady;
    a1 = courantReady;
    sendData = false;
    sei();

    Serial.write((uint8_t *)&a0, 2);
    Serial.write((uint8_t *)&a1, 2);
  }
}