#include "positions_sampler.h"
#include <Arduino.h>

volatile uint16_t adcValue;
volatile bool acquisitionActive = false;

void setup_ADC0()
{
    // ADC0 (pin A0)
    ADMUX = (1 << REFS0);                                                      // Référence de tension interne (5V)
    ADCSRA = 1 << ADEN | 1 << ADATE | 1 << ADIE | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0); // Enable interrupt quand conversion ADC est finie
    ADCSRB = (1 << ADTS2) | (1 << ADTS0);
    ADCSRA |= (1 << ADSC);                                                                    // Start première acquisition ADC
}

void setup_Timer1()
{
    // Timer 1 compare B trigger l'ADC
    TCCR1A = 0x00;
    TCCR1B = (1 << WGM12) | (1 << CS11) | (1 << CS10); // CTC, prescaler 64
    OCR1A = 249;      // 1 kHz si F_CPU = 16 MHz
    TIMSK1 = (1 << OCIE1A);  // interruption Compare Match A
}

ISR(TIMER1_COMPA_vect)
{
    ADCSRA |= (1 << ADSC);   // démarre conversion ADC
}

ISR(ADC_vect)
{
    if (!acquisitionActive)
    {
        return;
    }
    adcValue = ADC;
    Serial.write(lowByte(adcValue));  // octet bas
    Serial.write(highByte(adcValue)); // octet haut

    digitalWrite(13, !digitalRead(13)); // toggle LED
}