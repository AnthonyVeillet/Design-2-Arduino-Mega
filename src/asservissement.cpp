#include "asservissement.h"
#include "sampler.h"
#include "Arduino.h"
#include "PWM.h"

volatile uint8_t compteurCascade = 0;
volatile bool modeIdentification = false;
volatile bool mesureValide = true;
volatile uint16_t consigneCourant = 512; // Envoyer 50% = 0A par défaut
uint16_t commandePosition = 0;
uint16_t commandeCourant = 0;

// --- PID Timer ---
void setupTimerPID()
{
    // Timer2 en mode CTC
    TCCR2A = 0;
    TCCR2B = 0;
    TCNT2 = 0;

    TCCR2A |= (1 << WGM21); // CTC mode

    // Calcul OCR2A pour 1kHz
    // F_CPU = 16MHz, prescaler = 64, F_PID = 1000Hz
    // OCR2A = 16_000_000 / (64*1000) - 1 = 249
    OCR2A = 249;

    // Prescaler = 64
    TCCR2B |= (1 << CS22);

    // Activer interruption Compare Match A
    TIMSK2 |= (1 << OCIE2A);
}

uint16_t positionRef = 0;
CoefficientsPID_t coeffPosition = {0};
MemoireAsservissement_t memoireAsservissementPos = {0};

CoefficientsPID_t coeffCourant = {0};
MemoireAsservissement_t memoireAsservissementCourant = {0};

void tare()
{
    cli();
    // Accès section critique
    // positionRef = positionFiltre;
    positionRef = 430;
    sei();

    initCoeffsPID_Position(0, 1.12, 0);
    initCoeffsPI_Courant(2, 5);
}

void setPositionReference(uint16_t pref)
{
    positionRef = pref;
}

void initCoeffsPID_Position(float Kp, float Ki, float Kd)
{
    float Te = 0.01; // 100 Hz = fréquence asservissement position

    coeffPosition.b0 = Kp + (Ki * Te) / 2 + (2 * Kd) / Te;
    coeffPosition.b1 = (Ki * Te) - (4 * Kd) / Te;
    coeffPosition.b2 = -Kp + (Ki * Te) / 2 + (2 * Kd) / Te;
}

void resetPID()
{
    memoireAsservissementPos = {0};
    memoireAsservissementCourant = {0};
}

uint16_t printCounter = 0;

void calculCommandePosition(uint16_t position)
{
    float commande = 0;
    bool commandeSaturee = false;

    // Calcul de l'erreur
    float y_norm = position / 1023.0;
    float r_norm = positionRef / 1023.0;

    float erreur = y_norm - r_norm;
    // float erreur = position - positionRef; // position > positionRef: erreur positive
    // Serial.println(positionRef);

    // Valeurs pour calcul commande
    float e1 = memoireAsservissementPos.erreur1;
    float e2 = memoireAsservissementPos.erreur2;
    float u2 = memoireAsservissementPos.commande2;

    // Calcul commande PID
    commande = u2 + coeffPosition.b0 * erreur + coeffPosition.b1 * e1 + coeffPosition.b2 * e2;
    if (commande > 1.0 || commande < 0.0)
        commandeSaturee = true;
    else
        commandeSaturee = false;

    consigneCourant = convertCommandePWM(commande);
    commandePosition = consigneCourant;
    // consigneCourant = 0;
    // uint16_t pwm = convertCommandePWM(commande);

    // OCR3A = pwm;

    // Update valeurs mémoire
    if (!commandeSaturee)
    {
        // Anti-windup
        memoireAsservissementPos.commande2 = memoireAsservissementPos.commande1;
        memoireAsservissementPos.commande1 = commande;
    }
    memoireAsservissementPos.erreur2 = memoireAsservissementPos.erreur1;
    memoireAsservissementPos.erreur1 = erreur;
}

void initCoeffsPI_Courant(float Kp, float Ki)
{
    float Te = 0.001; // 1000 Hz = fréquence asservissement courant

    coeffCourant.b0 = Kp + (Ki * Te) / 2;
    coeffCourant.b1 = (Ki * Te) / 2 - Kp;
    coeffCourant.b2 = 0;
}

void calculCommandeCourant(uint16_t courant)
{
    float commande = 0;
    bool commandeSaturee = false;

    // normalisation
    float y_norm = courant / 1023.0;
    float r_norm = consigneCourant / 1023.0;

    // Calcul de l'erreur
    float erreur = y_norm - r_norm;

    // Valeurs pour calcul commande
    float e1 = memoireAsservissementCourant.erreur1;
    float u1 = memoireAsservissementCourant.commande1;

    // Calcul commande PID
    commande = u1 + coeffCourant.b0 * erreur + coeffCourant.b1 * e1;
    if (commande > 1.0 || commande < 0.0)
        commandeSaturee = true;
    else
        commandeSaturee = false;

    // saturation
    if (commande > 1.0)
        commande = 1.0;
    if (commande < 0.0)
        commande = 0.0;

    // sortie PWM
    // setNewDutyCycleValue(commande);
    uint16_t pwm = convertCommandePWM(commande);
    commandeCourant = pwm;
    OCR3A = pwm;

    // Update valeurs mémoire. Seulement besoin de -1.
    if (!commandeSaturee)
        memoireAsservissementCourant.commande1 = commande;
    memoireAsservissementCourant.erreur1 = erreur;
}

ISR(TIMER2_COMPA_vect)
{
    if (modeIdentification)
        return;

    // Lecture de la position filtrée (section critique)
    cli();
    uint16_t pos = positionFiltre;
    uint16_t courant = courantFiltre;
    sei();

    // Calcul PID
    compteurCascade++;
    if (compteurCascade >= 10)
    {
        // 100 Hz
        compteurCascade = 0;
        calculCommandePosition(pos);
    }
    // 1000 Hz
    calculCommandeCourant(courant);
}