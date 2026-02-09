#include <Arduino.h>
#include "positions_sampler.h"
#include "PWM.h"

const int ledPin = 13; // LED intégrée

void setup()
{
  Serial.begin(115200);
  while (!Serial)
  {
  }

  cli(); // désactiver interruptions
  pinMode(A0, INPUT);
  setup_Timer1();
  setup_ADC0();
  pinMode(10, OUTPUT); // PWM pin
  setup_Timer2();
  sei(); // réactiver interruptions

  pinMode(ledPin, OUTPUT); // LED
}

void loop()
{
  //   if (Serial.available()) {
  //     char cmd = Serial.read();
  //     if (cmd == 'S') {
  //         acquisitionActive = true;
  //         Serial.write('O');  // envoie ACK
  //     } else if (cmd == 'E') {
  //         acquisitionActive = false;
  //         Serial.write('K');  // ACK stop
  //     }
  // }
  // digitalWrite(13, !digitalRead(13)); // toggle LED

  setNewDutyCycleValue(50);
  delay(10);
}
