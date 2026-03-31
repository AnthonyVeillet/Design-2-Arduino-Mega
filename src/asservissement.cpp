#include "asservissement.h"
#include "sampler.h"
#include "Arduino.h"
#include "PWM.h"
#include <math.h>  // ===== AJOUT : pour cos() et M_PI =====

#define COMPTEUR_MESURE_VALIDE 20

volatile uint8_t compteurCascade = 0;
volatile bool modeIdentification = false;

volatile uint16_t consigneCourant = 512; // Envoyer 50% = 0A par défaut
volatile bool mesureValide = false;
MemoireConsigneCourant_t memoireConsigne = {0};

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

// ===== AJOUT : Instance du filtre notch pour la position =====
FiltreNotch_t filtreNotchPosition = {0};

void tare()
{
    cli();
    // Accès section critique
    // positionRef = positionFiltre;
    positionRef = 330;
    sei();

    initCoeffsPID_Position(0.07, 15, 0.012);
    initCoeffsPI_Courant(0.4, 165);

    // ===== AJOUT : Initialiser filtre notch à ~10 Hz, Fs=50 Hz, r=0.85 =====
    // r contrôle la largeur du notch : 0.85 = modéré, 0.9 = étroit, 0.8 = large
    initFiltreNotch(&filtreNotchPosition, 10.0, 50.0, 0.75);
}

void setPositionReference(uint16_t pref)
{
    positionRef = pref;
}

void initCoeffsPID_Position(float Kp, float Ki, float Kd)
{
    float Te = 0.02; // 50 Hz = fréquence asservissement position

    coeffPosition.b0 = Kp + (Ki * Te) / 2 + (2 * Kd) / Te;
    coeffPosition.b1 = (Ki * Te) - (4 * Kd) / Te;
    coeffPosition.b2 = -Kp + (Ki * Te) / 2 + (2 * Kd) / Te;
}

void resetPID()
{
    initCoeffsPID_Position(0.07, 15, 0.012);
    initCoeffsPI_Courant(0.4, 165);
    memoireAsservissementPos = {0};
    memoireAsservissementCourant = {0};

    // ===== AJOUT : Réinitialiser le filtre notch =====
    initFiltreNotch(&filtreNotchPosition, 10.0, 50.0, 0.85);
}

uint16_t printCounter = 0;
int8_t compteurMesureValide = 0;

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
    if (commande > 1.0 || commande < -1.0)
        commandeSaturee = true;
    else
        commandeSaturee = false;

    consigneCourant = convertCommandePWM(commande);
    commandePosition = consigneCourant;
    // consigneCourant = 0;
    // uint16_t pwm = convertCommandePWM(commande);

    // OCR3A = pwm;

    // Update valeurs mémoire
    memoireConsigne.consigne1 = consigneCourant;
    memoireConsigne.consigne2 = memoireConsigne.consigne1;
    memoireConsigne.consigne3 = memoireConsigne.consigne2;
    if (memoireConsigne.consigne3 - memoireConsigne.consigne1 <= 2 && erreur <= 0.002)
    {
        compteurMesureValide++;
        if (compteurMesureValide > COMPTEUR_MESURE_VALIDE)
        {
            compteurMesureValide = COMPTEUR_MESURE_VALIDE;
        }
    }
    else
    {
        compteurMesureValide--;
        if (compteurMesureValide < 0)
        {
            compteurMesureValide = 0;
        }
    }
    mesureValide = (compteurMesureValide == COMPTEUR_MESURE_VALIDE);

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

// ===== AJOUT : Implémentation filtre coupe-bande (notch) =====
// f0 = fréquence à rejeter (Hz)
// Fs = fréquence d'échantillonnage du filtre (Hz)
// r  = rayon des pôles (0 < r < 1). Plus r est proche de 1, plus le notch est étroit.
//      Valeurs typiques : 0.80 (large), 0.85 (modéré), 0.90 (étroit)
void initFiltreNotch(FiltreNotch_t* filtre, float f0, float Fs, float r)
{
    float w0 = 2.0 * M_PI * f0 / Fs;
    float cos_w0 = cos(w0);

    // Coefficients bruts du notch : H(z) = (1 - 2cos(w0)z^-1 + z^-2) / (1 - 2r·cos(w0)z^-1 + r²z^-2)
    float b0_raw = 1.0;
    float b1_raw = -2.0 * cos_w0;
    float b2_raw = 1.0;

    float a1_raw = -2.0 * r * cos_w0;
    float a2_raw = r * r;

    // Normalisation pour gain DC = 1 (ne pas affecter la mesure statique)
    float gain_dc = (b0_raw + b1_raw + b2_raw) / (1.0 + a1_raw + a2_raw);

    filtre->b0 = b0_raw / gain_dc;
    filtre->b1 = b1_raw / gain_dc;
    filtre->b2 = b2_raw / gain_dc;
    filtre->a1 = a1_raw;
    filtre->a2 = a2_raw;

    // Réinitialiser mémoire
    filtre->x1 = 0.0; filtre->x2 = 0.0;
    filtre->y1 = 0.0; filtre->y2 = 0.0;
}

float appliquerFiltreNotch(FiltreNotch_t* filtre, float x)
{
    float y = filtre->b0 * x + filtre->b1 * filtre->x1 + filtre->b2 * filtre->x2
            - filtre->a1 * filtre->y1 - filtre->a2 * filtre->y2;

    // Décaler mémoire
    filtre->x2 = filtre->x1;
    filtre->x1 = x;
    filtre->y2 = filtre->y1;
    filtre->y1 = y;

    return y;
}
// ===== FIN AJOUT =====

void calculCommandeCourant(uint16_t courant)
{
    float commande = 0;
    bool commandeSaturee = false;

    // normalisation
    float y_norm = courant / 1023.0;
    float r_norm = consigneCourant / 1023.0;

    // Calcul de l'erreur
    float erreur = r_norm - y_norm;

    // Valeurs pour calcul commande
    float e1 = memoireAsservissementCourant.erreur1;
    float u1 = memoireAsservissementCourant.commande1;

    // Calcul commande PID
    commande = u1 + coeffCourant.b0 * erreur + coeffCourant.b1 * e1;
    if (commande > 1.0 || commande < -1.0)
        commandeSaturee = true;
    else
        commandeSaturee = false;

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

volatile bool testCourant = false;
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
    if (compteurCascade >= 20)
    {
        // 50 Hz
        compteurCascade = 0;

        // ===== AJOUT : Appliquer filtre notch sur la position =====
        float posNotch = appliquerFiltreNotch(&filtreNotchPosition, (float)pos);
        if (posNotch > 1023.0) posNotch = 1023.0;
        if (posNotch < 0.0)    posNotch = 0.0;
        uint16_t posFiltree = (uint16_t)posNotch;
        // ===== FIN AJOUT =====

        calculCommandePosition(posFiltree);  // MODIFIÉ : était calculCommandePosition(pos)
        // if (testCourant)
        // {
        //     consigneCourant = 1000;
        // }
        // else
        // {
        //     consigneCourant = 0;
        // }
        // testCourant = !testCourant;
        // consigneCourant = positionRef;
    }
    // 1000 Hz
    calculCommandeCourant(courant);
}