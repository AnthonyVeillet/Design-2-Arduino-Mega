#pragma once

#include <stdint.h>

void setup_PWM();
void setNewDutyCycleValue(uint8_t dutyCycle);
extern uint16_t convertCommandePWM(float commande);