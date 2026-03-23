#pragma once

#include <stdint.h>

extern volatile bool modeIdentification;
extern volatile bool mesureValide;

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
extern void setPositionReference(uint16_t pref);
extern void initCoeffsPID_Position(float Kp, float Ki, float Kd);
extern void initCoeffsPI_Courant(float Kp, float Ki);
extern void tare();
extern void resetPID();
extern void calculCommandePosition(uint16_t position);
extern void calculCommandeCourant(uint16_t courant);