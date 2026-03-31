#include "asservissement.h"
#include "sampler.h"
#include "Arduino.h"
#include "PWM.h"

// ================= VARIABLES GLOBALES =================

volatile uint8_t compteurCascade = 0;
volatile bool modeIdentification = false;

// Gardé seulement si le .h le déclare encore en extern.
// Si tu as retiré mesureValide du .h, tu peux supprimer cette ligne.
volatile bool mesureValide = false;

// 512 = commande neutre
volatile uint16_t consigneCourant = 512;

uint16_t commandePosition = 512;
uint16_t commandeCourant  = 512;

uint16_t positionRef = 0;

CoefficientsPID_t coeffPosition = {0};
MemoireAsservissement_t memoireAsservissementPos = {0};

CoefficientsPID_t coeffCourant = {0};
MemoireAsservissement_t memoireAsservissementCourant = {0};

// ================= TIMER PID =================

void setupTimerPID()
{
    // Timer2 en mode CTC
    TCCR2A = 0;
    TCCR2B = 0;
    TCNT2 = 0;

    TCCR2A |= (1 << WGM21); // CTC mode

    // F_CPU = 16MHz, prescaler = 64, F_PID = 1000Hz
    // OCR2A = 16_000_000 / (64 * 1000) - 1 = 249
    OCR2A = 249;

    // Prescaler = 64
    TCCR2B |= (1 << CS22);

    // Activer interruption Compare Match A
    TIMSK2 |= (1 << OCIE2A);
}

// ================= COMMANDES =================

void tare()
{
    cli();
    positionRef = positionFiltre;  // tare réelle sur la position actuelle
    consigneCourant = 512;
    sei();
}

void setPositionReference(uint16_t pref)
{
    positionRef = pref;
}

void resetPID()
{
    memoireAsservissementPos = {0};
    memoireAsservissementCourant = {0};

    consigneCourant   = 512;
    commandePosition  = 512;
    commandeCourant   = 512;
}

// ================= COEFFICIENTS =================

void initCoeffsPID_Position(float Kp, float Ki, float Kd)
{
    float Te = 0.02f; // 50 Hz = fréquence boucle position

    coeffPosition.b0 = Kp + (Ki * Te) / 2.0f + (2.0f * Kd) / Te;
    coeffPosition.b1 = (Ki * Te) - (4.0f * Kd) / Te;
    coeffPosition.b2 = -Kp + (Ki * Te) / 2.0f + (2.0f * Kd) / Te;
}

void initCoeffsPI_Courant(float Kp, float Ki)
{
    float Te = 0.001f; // 1000 Hz = fréquence boucle courant

    coeffCourant.b0 = Kp + (Ki * Te) / 2.0f;
    coeffCourant.b1 = (Ki * Te) / 2.0f - Kp;
    coeffCourant.b2 = 0.0f;
}

// ================= BOUCLE POSITION =================

void calculCommandePosition(uint16_t position)
{
    // Calcul de l'erreur
    float y_norm = position / 1023.0f;
    float r_norm = positionRef / 1023.0f;
    float erreur = y_norm - r_norm;

    // Mémoires
    float e1 = memoireAsservissementPos.erreur1;
    float e2 = memoireAsservissementPos.erreur2;
    float u2 = memoireAsservissementPos.commande2;

    // Commande non saturée
    float commandeUnsat = u2
                        + coeffPosition.b0 * erreur
                        + coeffPosition.b1 * e1
                        + coeffPosition.b2 * e2;

    // Saturation explicite
    float commandeSat = commandeUnsat;
    if (commandeSat > 1.0f)
        commandeSat = 1.0f;
    else if (commandeSat < -1.0f)
        commandeSat = -1.0f;

    // Toujours envoyer la commande saturée
    consigneCourant = convertCommandePWM(commandeSat);
    commandePosition = consigneCourant;

    // Anti-windup conditionnel
    bool pousseVersHaut = (erreur > 0.0f);
    bool pousseVersBas  = (erreur < 0.0f);

    bool bloqueIntegration =
        (commandeSat >= 1.0f && pousseVersHaut) ||
        (commandeSat <= -1.0f && pousseVersBas);

    if (!bloqueIntegration)
    {
        memoireAsservissementPos.commande2 = memoireAsservissementPos.commande1;
        memoireAsservissementPos.commande1 = commandeSat;
    }

    // Mise à jour erreurs
    memoireAsservissementPos.erreur2 = memoireAsservissementPos.erreur1;
    memoireAsservissementPos.erreur1 = erreur;
}

// ================= BOUCLE COURANT =================

void calculCommandeCourant(uint16_t courant)
{
    // Normalisation
    float y_norm = courant / 1023.0f;
    float r_norm = consigneCourant / 1023.0f;

    // Erreur
    float erreur = r_norm - y_norm;

    // Mémoires
    float e1 = memoireAsservissementCourant.erreur1;
    float u1 = memoireAsservissementCourant.commande1;

    // Commande non saturée
    float commandeUnsat = u1
                        + coeffCourant.b0 * erreur
                        + coeffCourant.b1 * e1;

    // Saturation explicite
    float commandeSat = commandeUnsat;
    if (commandeSat > 1.0f)
        commandeSat = 1.0f;
    else if (commandeSat < -1.0f)
        commandeSat = -1.0f;

    // Sortie PWM
    uint16_t pwm = convertCommandePWM(commandeSat);
    commandeCourant = pwm;
    OCR3A = pwm;

    // Anti-windup conditionnel
    bool pousseVersHaut = (erreur > 0.0f);
    bool pousseVersBas  = (erreur < 0.0f);

    bool bloqueIntegration =
        (commandeSat >= 1.0f && pousseVersHaut) ||
        (commandeSat <= -1.0f && pousseVersBas);

    if (!bloqueIntegration)
    {
        memoireAsservissementCourant.commande1 = commandeSat;
    }

    memoireAsservissementCourant.erreur1 = erreur;
}

// ================= ISR =================

volatile bool testCourant = false;

ISR(TIMER2_COMPA_vect)
{
    if (modeIdentification)
        return;

    // Lecture des mesures filtrées
    uint16_t pos = positionFiltre;
    uint16_t courant = courantFiltre;

    // Boucle position à 50 Hz
    compteurCascade++;
    if (compteurCascade >= 20)
    {
        compteurCascade = 0;
        calculCommandePosition(pos);
    }

    // Boucle courant à 1000 Hz
    calculCommandeCourant(courant);
}