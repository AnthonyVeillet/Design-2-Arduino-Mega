#include <Arduino.h>
#include "adc_sampler.h"

#ifndef SERIAL_BAUD
#define SERIAL_BAUD 2000000
#endif

#ifndef ADC_PIN
#define ADC_PIN 0
#endif

#ifndef VREF_VOLTS
#define VREF_VOLTS 5.0
#endif

static uint32_t g_fs = 1000;
static bool g_streaming = false;

// Format binaire: 2 bytes ADC little-endian
static inline void sendSampleBinary(uint16_t adc) {
  uint8_t b[2];
  b[0] = (uint8_t)(adc & 0xFF);
  b[1] = (uint8_t)((adc >> 8) & 0xFF);
  Serial.write(b, 2);
}

static void printHelp() {
  Serial.println(F("Commands:"));
  Serial.println(F("  FS=xxxx        set sampling frequency (Hz)"));
  Serial.println(F("  START          start streaming binary samples"));
  Serial.println(F("  STOP           stop sampling"));
  Serial.println(F("  INFO           print current config"));
  Serial.println(F("  HELP           this help"));
  Serial.println();
}

static void printInfo() {
  Serial.print(F("FS_HZ=")); Serial.println(g_fs);
  Serial.print(F("ADC_PIN=A")); Serial.println(ADC_PIN);
  Serial.print(F("VREF_VOLTS=")); Serial.println(VREF_VOLTS, 6);
  Serial.print(F("DROPPED=")); Serial.println(ADCSampler::dropped());
}

static void handleLine(String line) {
  line.trim();
  line.toUpperCase();

  if (line.startsWith("FS=")) {
    uint32_t v = (uint32_t) line.substring(3).toInt();
    if (v < 1) v = 1;
    g_fs = v;

    if (g_streaming) {
      ADCSampler::stop();
      ADCSampler::begin(g_fs, ADC_PIN);
    }

    Serial.print(F("OK FS=")); Serial.println(g_fs);
  } else if (line == "START") {
    ADCSampler::stop();
    ADCSampler::begin(g_fs, ADC_PIN);
    g_streaming = true;

    // Petit header texte (une fois) avant le binaire
    Serial.println(F("#BEGIN"));
    Serial.print(F("#FS_HZ=")); Serial.println(g_fs);
    Serial.print(F("#VREF_VOLTS=")); Serial.println(VREF_VOLTS, 6);
    Serial.println(F("#FORMAT=BIN16_ADC_LE"));
    Serial.println(F("#ENDHDR"));
  } else if (line == "STOP") {
    g_streaming = false;
    ADCSampler::stop();
    Serial.println(F("#STOPPED"));
    printInfo();
  } else if (line == "INFO") {
    printInfo();
  } else if (line == "HELP") {
    printHelp();
  } else if (line.length() > 0) {
    Serial.println(F("ERR Unknown command. Type HELP"));
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  while (!Serial) {}

  // Si tu utilises une référence externe sur AREF, décommente:
  // analogReference(EXTERNAL);

  Serial.println(F("#READY"));
  printHelp();
  printInfo();
}

void loop() {
  // Read commands
  static String line;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleLine(line);
      line = "";
    } else if (c != '\r') {
      line += c;
      if (line.length() > 80) line = line.substring(0, 80);
    }
  }

  // Stream samples (binary)
  if (g_streaming) {
    while (ADCSampler::available()) {
      Sample16 s = ADCSampler::read();
      sendSampleBinary(s.adc);
    }
  }
}
