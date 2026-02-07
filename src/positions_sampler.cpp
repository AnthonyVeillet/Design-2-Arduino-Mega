#include "positions_sampler.h"
#include <Arduino.h>

volatile uint16_t adcValue;

void setup_ADC0()
{
    // ADC0 (pin A0)
    ADMUX = 1 << REFS0;                                                                       // Référence de tension interne (5V)
    ADCSRA = 1 << ADEN | 1 << ADATE | 1 << ADIE | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0); // Enable interrupt quand conversion ADC est finie
    ADCSRA |= (1 << ADSC);                                                                    // Start première acquisition ADC
}

void setup_Timer1()
{
    // Timer 1 compare B trigger l'ADC
    ADCSRB = (1 << ADTS2) | (1 << ADTS0);
    TCCR1A = 0;                                        // Mode normal
    TCCR1B = (1 << WGM12) | (1 << CS11) | (1 << CS10); // Fréquence de 250kHz pour le compteur
    OCR1A = 249;                                       // Compte 250 / 250000 -> 1ms -> 1kHz
    OCR1B = 249;
    TIMSK1 = 0; // Pas d'interrupt
}

ISR(ADC_vect) {
  adcValue = ADC;
  Serial.write(lowByte(adcValue));   // octet bas
  Serial.write(highByte(adcValue));  // octet haut
}