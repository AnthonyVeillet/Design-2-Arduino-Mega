#include "asservissement.h"
#include "sampler.h"
#include "Arduino.h"

uint16_t positionRef = 0;
CoefficientsPID_t coeffPosition = {0};
OldValAsservissementPos_t memoireAsservissementPos = {0};

uint16_t courantRef = 0;
CoefficientsPID_t coeffCourant = {0};
OldValAsservissementPos_t memoireAsservissementCourant = {0};

void tare()
{
    cli();
    // Accès section critique
    positionRef = positionFiltre;
    courantRef = courantFiltre;
    sei();

    // initCoeffsPID_Position();
}

void initCoeffsPID_Position(float Kp, float Ki, float Kd, float Te, float Ti, float Td)
{
    coeffPosition.b0 = Kp + (Ki*Te)/(2*Ti) + (2*Kd*Td)/Te;
    coeffPosition.b1 = (Ki*Te)/Ti - (4*Kd*Td)/Te;
    coeffPosition.b2 = -Kp + (Ki*Te)/(2*Ti) + (2*Kd*Td)/Te;
}

void calculCommandePosition(uint16_t position)
{
    float commande = 0;

    // Calcul de l'erreur
    float erreur = position - positionRef; // position > positionRef: erreur positive

    // Valeurs pour calcul commande
    float e1 = memoireAsservissementPos.erreur1;
    float e2 = memoireAsservissementPos.erreur2;
    float u2 = memoireAsservissementPos.commande2;

    // Calcul commande PID
    commande = u2 + coeffPosition.b0*erreur + coeffPosition.b1*e1 + coeffPosition.b2*e2;

    // Update valeurs mémoire
    memoireAsservissementPos.commande2 = memoireAsservissementPos.commande1;
    memoireAsservissementPos.commande1 = commande;
    memoireAsservissementPos.erreur2 = memoireAsservissementPos.erreur1;
    memoireAsservissementPos.erreur1 = erreur;
}

void calculCommandeCourant(uint16_t courant)
{
}