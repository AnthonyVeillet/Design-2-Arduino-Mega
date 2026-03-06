#pragma once

#include <stdint.h>

#define ADC_POSITION_A0 0
#define ADC_COURANT_A1 1

// Fonctions
extern void setup_ADC();

// Variables partagées
extern volatile bool acquisitionActive;
extern volatile bool sendData;

extern volatile uint16_t positionFiltre;
extern volatile uint16_t courantFiltre;

// Nouvelles variables minimales pour transmettre une vraie donnée décimée
extern volatile uint16_t positionReady;
extern volatile uint16_t courantReady;