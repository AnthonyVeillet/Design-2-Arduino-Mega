#pragma once

#include "stdint.h"

// Fonctions
extern void setup_ADC();
extern void setup_Timer1();

extern volatile bool acquisitionActive;
extern volatile bool sendData;
extern volatile uint16_t adcValues[2];