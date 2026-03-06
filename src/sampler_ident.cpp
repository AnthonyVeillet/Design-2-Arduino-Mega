#include "sampler_ident.h"
#include <Arduino.h>

volatile uint16_t adcValues[2] = {0, 0};
const uint8_t ADC_PINS[] = {A0, A1};

volatile uint8_t nextChannel = 0;
volatile uint8_t activeChannel = 0;

volatile bool acquisitionActive = false;
volatile uint16_t toggleCounter = 0;
volatile bool sendData = false;

// Nouvelles variables minimales pour l'envoi au PC
volatile uint16_t positionReady = 0;
volatile uint16_t courantReady = 0;

// Décimation, 5 kHz par capteur -> 500 Hz envoyé au PC
volatile uint8_t decimationCounter = 0;

#define TAILLE_BUFFER_FILTRE_POSITION 10 // Maximum de 256
uint16_t bufferFiltrePosition[TAILLE_BUFFER_FILTRE_POSITION] = {0};
uint8_t indexFiltrePosition = 0;
uint32_t  sommePosition = 0;
volatile uint16_t positionFiltre = 0;

#define TAILLE_BUFFER_FILTRE_COURANT 10 // Maximum de 256
uint16_t bufferFiltreCourant[TAILLE_BUFFER_FILTRE_COURANT] = {0};
uint8_t indexFiltreCourant = 0;
uint32_t  sommeCourant = 0;
volatile uint16_t courantFiltre = 0;

void filtrePosition(uint16_t newPosition);
void filtreCourant(uint16_t newCourant);

void setup_ADC()
{
    pinMode(A0, INPUT);
    pinMode(A1, INPUT);

    // -----------------------------
    // Timer1 : 10 kHz de déclenchement
    // Comme on alterne A0 et A1, chaque capteur est lu à 5 kHz
    // -----------------------------
    TCCR1A = 0;
    TCCR1B = 0;
    TCNT1 = 0;

    // Mode CTC : WGM12 = 1
    TCCR1B |= (1 << WGM12);

    // Compare Match A : OCR1A = (F_CPU / (prescaler * f)) - 1
    // F_CPU = 16 MHz, f = 5 kHz, prescaler = 8
    // OCR1A = 16,000,000 / (8*10000) - 1 = 199
    OCR1A = 199;

    // Prescaler = 8
    TCCR1B |= (1 << CS11);

    // Enable Timer1 Compare Match A interrupt
    TIMSK1 |= (1 << OCIE1A);

    // -----------------------------
    // ADC configuration
    // -----------------------------
    ADMUX = (1 << REFS0);                   // AVcc comme référence, canal sera sélectionné dynamiquement
    ADCSRA = (1 << ADEN)                    // activer ADC
             | (1 << ADIE)                  // activer interruption ADC
             | (1 << ADPS2) | (1 << ADPS1); // 64 prescaler → ADC clock = 250 kHz
}

ISR(TIMER1_COMPA_vect)
{
    // sélectionner canal
    ADMUX = (ADMUX & 0xF0) | (ADC_PINS[nextChannel] - A0);

    // mémoriser le canal en conversion
    activeChannel = nextChannel;

    // démarrer conversion
    ADCSRA |= (1 << ADSC);

    // prochain canal
    if (nextChannel == ADC_POSITION_A0)
        nextChannel = ADC_COURANT_A1;
    else
        nextChannel = ADC_POSITION_A0;
}

ISR(ADC_vect)
{
    adcValues[activeChannel] = ADC;

    if (activeChannel == ADC_POSITION_A0)
    {
        filtrePosition(adcValues[activeChannel]);
    }
    else
    {
        filtreCourant(adcValues[activeChannel]);

        // On ne décime qu'après avoir reçu le 2e canal,
        // donc après une paire complète {position, courant}
        if (acquisitionActive)
        {
            decimationCounter++;

            if (decimationCounter >= 10)
            {
                positionReady = positionFiltre;
                courantReady = courantFiltre;
                sendData = true;
                decimationCounter = 0;
            }
        }
    }

    toggleCounter++;
    if (toggleCounter >= 5000)
    {
        digitalWrite(13, !digitalRead(13));
        toggleCounter = 0;
    }
}

void filtrePosition(uint16_t newPosition)
{
    // Remplacer ancienne valeur par nouvelle dans buffer et somme
    sommePosition -= bufferFiltrePosition[indexFiltrePosition];
    sommePosition += newPosition;
    bufferFiltrePosition[indexFiltrePosition] = newPosition;

    // update index
    indexFiltrePosition++;
    if (indexFiltrePosition >= TAILLE_BUFFER_FILTRE_POSITION)
        indexFiltrePosition = 0;

    // update position filtrée
    positionFiltre = sommePosition / TAILLE_BUFFER_FILTRE_POSITION;
}

void filtreCourant(uint16_t newCourant)
{
    // Remplacer ancienne valeur par nouvelle dans buffer et somme
    sommeCourant -= bufferFiltreCourant[indexFiltreCourant];
    sommeCourant += newCourant;
    bufferFiltreCourant[indexFiltreCourant] = newCourant;

    // update index
    indexFiltreCourant++;
    if (indexFiltreCourant >= TAILLE_BUFFER_FILTRE_COURANT)
        indexFiltreCourant = 0;

    // update position filtrée
    courantFiltre = sommeCourant / TAILLE_BUFFER_FILTRE_COURANT;
}