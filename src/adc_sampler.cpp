#include "adc_sampler.h"
#include <avr/interrupt.h>

// --- Ring buffer local au fichier (simple + ISR-friendly) ---
static constexpr uint16_t BUF_SIZE = 2048; // power of 2
static volatile uint16_t g_head = 0;
static volatile uint16_t g_tail = 0;
static volatile uint32_t g_drop_count = 0;
static volatile bool g_running = false;
static volatile uint16_t g_buf[BUF_SIZE];

static inline uint16_t nextIndex(uint16_t idx) {
  return (uint16_t)((idx + 1) & (BUF_SIZE - 1));
}

void ADCSampler::begin(uint32_t fs_hz, uint8_t adc_pin) {
  cli();
  g_head = 0;
  g_tail = 0;
  g_drop_count = 0;
  g_running = false;

  setupADC(adc_pin);
  setupTimer1(fs_hz);

  // Enable ADC interrupt + Auto Trigger + Start
  ADCSRA |= _BV(ADIE) | _BV(ADATE) | _BV(ADSC);

  g_running = true;
  sei();
}

void ADCSampler::stop() {
  cli();
  g_running = false;

  ADCSRA &= ~_BV(ADIE);
  ADCSRA &= ~_BV(ADATE);

  // Stop Timer1
  TCCR1B = 0;
  TIMSK1 = 0;
  sei();
}

bool ADCSampler::available() {
  return g_head != g_tail;
}

Sample16 ADCSampler::read() {
  Sample16 s{0};

  cli();
  if (g_head != g_tail) {
    // Lire une valeur volatile -> copier en local
    uint16_t val = g_buf[g_tail];
    g_tail = nextIndex(g_tail);
    s.adc = val;
  }
  sei();

  return s;
}

uint32_t ADCSampler::dropped() {
  uint32_t d;
  cli();
  d = g_drop_count;
  sei();
  return d;
}

void ADCSampler::setupADC(uint8_t adc_pin) {
  // Reference AVcc (5V)
  ADMUX = 0;
  ADMUX |= _BV(REFS0);

  adc_pin &= 0x07;
  ADMUX = (ADMUX & 0xF0) | adc_pin;

  // Prescaler 128 => ADC clock 125 kHz (bon pour précision)
  ADCSRA = 0;
  ADCSRA |= _BV(ADEN);
  ADCSRA |= _BV(ADPS2) | _BV(ADPS1) | _BV(ADPS0);

  // Auto trigger source = Timer1 Compare Match A (ADTS=0b101)
  ADCSRB = 0;
  ADCSRB |= _BV(ADTS2) | _BV(ADTS0);

  // Disable digital input buffer on ADC pin
  DIDR0 |= (1 << adc_pin);
}

void ADCSampler::setupTimer1(uint32_t fs_hz) {
  const uint32_t prescalers[] = {1, 8, 64, 256, 1024};
  const uint16_t cs_bits[] = {
    _BV(CS10),
    _BV(CS11),
    _BV(CS11) | _BV(CS10),
    _BV(CS12),
    _BV(CS12) | _BV(CS10)
  };

  uint32_t best_ocr = 0;
  uint16_t best_cs = 0;

  for (uint8_t i = 0; i < 5; i++) {
    uint32_t p = prescalers[i];
    uint32_t ocr = (F_CPU / (p * fs_hz));
    if (ocr == 0) continue;
    ocr -= 1;
    if (ocr <= 65535) {
      best_ocr = ocr;
      best_cs = cs_bits[i];
      break;
    }
  }

  // Timer1 CTC
  TCCR1A = 0;
  TCCR1B = 0;
  TCCR1B |= _BV(WGM12);
  OCR1A = (uint16_t)best_ocr;

  // Start timer
  TCCR1B |= best_cs;

  // No interrupt needed
  TIMSK1 = 0;
}

ISR(ADC_vect) {
  if (!g_running) return;

  uint16_t h = g_head;
  uint16_t n = nextIndex(h);

  if (n == g_tail) {
    g_drop_count++;
    return;
  }

  uint16_t val = ADC; // 10-bit
  g_buf[h] = val;
  g_head = n;
}
