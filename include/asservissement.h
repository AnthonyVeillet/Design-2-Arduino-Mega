#pragma once

#include <stdint.h>

extern bool modeIdentification;

typedef struct{
    float commande1; // dernière commande
    float commande2; // avant-dernière commande
    float erreur1; // dernière erreur
    float erreur2; // avant-dernière erreur
} MemoireAsservissement_t;

typedef struct{
    float b0;
    float b1;
    float b2;
} CoefficientsPID_t;

extern void setupTimerPID();
extern void tare();
extern void resetPID();
extern void calculCommandePosition(uint16_t position);
extern void calculCommandeCourant(uint16_t courant);