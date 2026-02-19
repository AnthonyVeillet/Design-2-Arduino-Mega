#include "positions_sampler.h"
#include <Arduino.h>

volatile uint16_t adcValues[2] = {0, 0};
const uint8_t ADC_PINS[] = {A0, A1};
volatile uint8_t currentChannel = 0;
volatile bool acquisitionActive = false;
volatile uint16_t toggleCounter = 0;
volatile bool sendData = false;

void setup_ADC()
{

    pinMode(A0, INPUT);
    pinMode(A1, INPUT);
    // -----------------------------
    // Timer1 pour trigger ADC 5 kHz
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
    ADMUX = (1 << REFS0);                                  // AVcc comme référence, canal sera sélectionné dynamiquement
    ADCSRA = (1 << ADEN)                                   // activer ADC
             | (1 << ADIE)                                 // activer interruption ADC
             | (1 << ADPS2) | (1 << ADPS1);  // 64 prescaler → ADC clock = 250 kHz
}

ISR(TIMER1_COMPA_vect)
{
    // Sélection du canal A0 ou A1
    ADMUX = (ADMUX & 0xF0) | (ADC_PINS[currentChannel] - A0); // choisir canal

    // Démarrer conversion ADC
    ADCSRA |= (1 << ADSC);

    // Passer au canal suivant pour la prochaine acquisition
    currentChannel = (currentChannel + 1) % 2;
}

ISR(ADC_vect)
{
    if (!acquisitionActive)
    {
        return;
    }
    adcValues[(currentChannel + 1) % 2] = ADC;

    uint16_t a0 = adcValues[0];
    uint16_t a1 = adcValues[1];

    toggleCounter++;
    if (toggleCounter >= 5000) // divise fréquence pour LED (~1 Hz)
    {
        digitalWrite(13, !digitalRead(13));
        toggleCounter = 0;
    }
}