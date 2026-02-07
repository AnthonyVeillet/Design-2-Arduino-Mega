#include <Arduino.h>
#include "positions_sampler.h"
#include "PWM.h"

void setup()
{
  Serial.begin(115200);
  while (!Serial)
  {
  }

  cli(); // désactiver interruptions
  // setup_Timer1();
  // setup_ADC0();
  pinMode(10, OUTPUT); // PWM pin
  setup_Timer2();
  sei(); // réactiver interruptions
}

void loop()
{
  
  setNewDutyCycleValue(100);
  delay(500);
}
