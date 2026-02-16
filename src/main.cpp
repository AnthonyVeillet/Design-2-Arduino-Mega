#include <Arduino.h>
#include "positions_sampler.h"
#include "PWM.h"

const int ledPin = 13; // LED intégrée

void setup()
{
  pinMode(ledPin, OUTPUT); // LED

  cli(); // désactiver interruptions
  setup_ADC();
  setup_PWM();
  sei(); // réactiver interruptions
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


}
