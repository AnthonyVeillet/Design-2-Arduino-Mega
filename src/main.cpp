#include <Arduino.h>
#include "sampler.h"
#include "PWM.h"
#include "asservissement.h"

const int ledPin = 13; // LED intégrée
const int massePin = 2;

uint16_t positionVal = 0;
uint16_t courantVal = 0;

void setup()
{
  Serial.begin(115200);
  pinMode(ledPin, OUTPUT); // LED

  pinMode(massePin, OUTPUT);

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
    else if (cmd == 'Z')
    {
      resetPID();
    }
    else if (cmd == 'P')
    {
      while (Serial.available() < 1)
        ;
      uint8_t pwm = Serial.read(); // 0–100

      setNewDutyCycleValue(pwm / 100.0f);
    }
    // Consigne position
    else if (cmd == 'R')
    {
      while (Serial.available() < 2)
        ;
      uint16_t ref = Serial.read() | (Serial.read() << 8);
      setPositionReference(ref);
    }
    // PID position (Kp Ki Kd float)
    else if (cmd == 'G')
    {
      while (Serial.available() < 12)
        ;
      float kp, ki, kd;
      Serial.readBytes((char *)&kp, 4);
      Serial.readBytes((char *)&ki, 4);
      Serial.readBytes((char *)&kd, 4);
      initCoeffsPID_Position(kp, ki, kd);
    }
    // PID courant (Kp Ki)
    else if (cmd == 'H')
    {
      while (Serial.available() < 8)
        ;
      float kp, ki;
      Serial.readBytes((char *)&kp, 4);
      Serial.readBytes((char *)&ki, 4);
      initCoeffsPI_Courant(kp, ki);
    }
    else if (cmd == 'M')
    {
      while (Serial.available() < 1)
        ;
      bool masseStable = Serial.read(); // true ou false
      digitalWrite(massePin, masseStable);
    }
  }

  // Envoi du courant en continu quand la position est asservie pour afficher la masse.
  // Envoi en continu des commandes des deux régulateurs.
  if (toggleCounter % 10 == 0)
  {
    cli();
    uint16_t pos = positionFiltre;
    uint16_t cur = courantFiltre;
    uint16_t cmd_pos = commandePosition;
    uint16_t cmd_cur = commandeCourant;
    sei();

    Serial.write('T');
    Serial.write((uint8_t *)&pos, 2);
    Serial.write((uint8_t *)&cur, 2);
    Serial.write((uint8_t *)&cmd_pos, 2);
    Serial.write((uint8_t *)&cmd_cur, 2);
    Serial.write(mesureValide ? 1 : 0);
  }

  toggleCounter++;
  if (toggleCounter >= 5000)
  {
    digitalWrite(13, !digitalRead(13));
    toggleCounter = 0;
  }
}
