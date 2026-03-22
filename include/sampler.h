#pragma once

#include "stdint.h"

#define ADC_POSITION_A0 0
#define ADC_COURANT_A1 1

// Fonctions
extern void setup_ADC();
extern void setup_Timer1();

extern volatile bool acquisitionActive;
extern volatile uint16_t positionFiltre;
extern volatile uint16_t courantFiltre;
extern volatile uint16_t adcValues[2];
