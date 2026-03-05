#include "sampler.h"
#include <Arduino.h>

volatile uint16_t adcValues[2] = {0, 0};
const uint8_t ADC_PINS[] = {A0, A1};

volatile uint8_t nextChannel = 0;
volatile uint8_t activeChannel = 0;

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
    if (!acquisitionActive)
        return;

    // stockage clair avec define
    adcValues[activeChannel] = ADC;

    toggleCounter++;
    if (toggleCounter >= 5000)
    {
        digitalWrite(13, !digitalRead(13));
        toggleCounter = 0;
    }
}