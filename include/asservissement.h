#pragma once

#include <stdint.h>

extern volatile bool modeIdentification;
extern volatile bool mesureValide;
extern uint16_t commandePosition;
extern uint16_t commandeCourant;

typedef struct{
    float commande1; // dernière commande
    float commande2; // avant-dernière commande
    float erreur1; // dernière erreur
    float erreur2; // avant-dernière erreur
} MemoireAsservissement_t;

typedef struct{
    uint16_t consigne1;
    uint16_t consigne2;
    uint16_t consigne3;
} MemoireConsigneCourant_t;

typedef struct{
    float b0;
    float b1;
    float b2;
} CoefficientsPID_t;

// ===== AJOUT : Filtre coupe-bande (notch) pour résonance =====
typedef struct{
    float b0, b1, b2;  // coefficients numérateur
    float a1, a2;       // coefficients dénominateur
    float x1, x2;       // mémoire entrée (x[n-1], x[n-2])
    float y1, y2;       // mémoire sortie (y[n-1], y[n-2])
} FiltreNotch_t;

extern void setupTimerPID();
extern void setPositionReference(uint16_t pref);
extern void initCoeffsPID_Position(float Kp, float Ki, float Kd);
extern void initCoeffsPI_Courant(float Kp, float Ki);
extern void tare();
extern void resetPID();
extern void calculCommandePosition(uint16_t position);
extern void calculCommandeCourant(uint16_t courant);

// ===== AJOUT : Fonctions filtre notch =====
extern void initFiltreNotch(FiltreNotch_t* filtre, float f0, float Fs, float r);
extern float appliquerFiltreNotch(FiltreNotch_t* filtre, float x);