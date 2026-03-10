#include "asservissement.h"
#include "sampler.h"
#include "Arduino.h"
#include "PWM.h"

volatile uint8_t compteurCascade = 0;

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

void initCoeffsPID_Position();

uint16_t positionRef = 0;
CoefficientsPID_t coeffPosition = {0};
MemoireAsservissement_t memoireAsservissementPos = {0};

uint16_t courantRef = 0;
CoefficientsPID_t coeffCourant = {0};
MemoireAsservissement_t memoireAsservissementCourant = {0};

void tare()
{
    cli();
    // Accès section critique
    positionRef = positionFiltre;
    courantRef = courantFiltre;
    sei();

    initCoeffsPID_Position();
}

void initCoeffsPID_Position()
{
    float Kp = 3.8;
    float Ki = 1;
    float Kd = 0.1;

    float Te = 0.0002; // 5 kHz
    float Ti = 0.3;
    float Td = 0.013;

    coeffPosition.b0 = Kp + (Ki * Te) / (2 * Ti) + (2 * Kd * Td) / Te;
    coeffPosition.b1 = (Ki * Te) / Ti - (4 * Kd * Td) / Te;
    coeffPosition.b2 = -Kp + (Ki * Te) / (2 * Ti) + (2 * Kd * Td) / Te;
}

uint16_t printCounter = 0;

void calculCommandePosition(uint16_t position)
{
    float commande = 0;

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
    // Serial.print(commande);
    // uint16_t pwm = convertCommandePWM(commande);
    // if (printCounter > 200)
    // {
    //     Serial.println(commande);
    //     printCounter = 0;
    //     // Serial.println(commande);
    // }
    // printCounter++;

    // OCR3A = pwm;

    // Update valeurs mémoire
    memoireAsservissementPos.commande2 = memoireAsservissementPos.commande1;
    memoireAsservissementPos.commande1 = commande;
    memoireAsservissementPos.erreur2 = memoireAsservissementPos.erreur1;
    memoireAsservissementPos.erreur1 = erreur;
}

uint16_t calculConsigneCourant(uint16_t commandePosition){
    uint16_t consigne = 0;

    

    return consigne;
}

void initCoeffsPI_Courant(float Kp, float Ki, float Te, float Ti)
{
    coeffCourant.b0 = Kp + (Ki * Te) / (2 * Ti);
    coeffCourant.b1 = (Ki * Te) / (2 * Ti) - Kp;
    coeffCourant.b2 = 0;
}

void calculCommandeCourant(uint16_t courant)
{
    float commande = 0;

    // normalisation
    float y_norm = courant / 1023.0;
    float r_norm = courantRef / 1023.0;

    // Calcul de l'erreur
    float erreur = r_norm - y_norm;

    // Valeurs pour calcul commande
    float e1 = memoireAsservissementCourant.erreur1;
    float u1 = memoireAsservissementCourant.commande1;

    // Calcul commande PID
    commande = u1 + coeffCourant.b0 * erreur + coeffCourant.b1 * e1;

    // saturation
    if (commande > 1.0) commande = 1.0;
    if (commande < 0.0) commande = 0.0;

    // sortie PWM
    setNewDutyCycleValue(commande);

    // Update valeurs mémoire. Seulement besoin de -1.
    memoireAsservissementCourant.commande1 = commande;
    memoireAsservissementCourant.erreur1 = erreur;
}

ISR(TIMER2_COMPA_vect)
{
    // Lecture de la position filtrée (section critique)
    cli();
    uint16_t pos = positionFiltre;
    uint16_t courant = courantFiltre;
    sei();

    // Calcul PID
    compteurCascade++;
    if (compteurCascade >= 10)
    {
        compteurCascade = 0;
        calculCommandePosition(pos);
    }
    calculCommandeCourant(courant);
}