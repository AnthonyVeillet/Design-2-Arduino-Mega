"""
Simulateur série pour tester sans Arduino.
Imite le protocole de main.cpp :
  - Répond 'O' à la commande 'S' (start)
  - Envoie des paquets 'T' (1 + 8 octets) à ~50 Hz quand actif
  - Le courant varie légèrement autour d'un point de repos,
    et se décale quand on simule une masse.
"""

import struct
import threading
import time
import random


class FakeSerial:
    """Remplace serial.Serial pour tester sans Arduino physique."""

    def __init__(self, port="FAKE", baudrate=115200, timeout=0, write_timeout=None):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

        self._rx_buffer = bytearray()   # Buffer de lecture (PC lit ici)
        self._lock = threading.Lock()

        self._acquisition = False
        self._running = True
        self._pwm = 50                  # PWM en % (50 = neutre)

        # Simulation capteurs
        self._position_base = 430       # Position de repos
        self._courant_base = 512        # Courant de repos (milieu ADC 10 bits)
        self._masse_offset = 0          # Décalage courant simulé (simule une masse)

        # Thread d'envoi de paquets 'T'
        self._thread = threading.Thread(target=self._packet_sender, daemon=True)
        self._thread.start()

    # --- Interface serial.Serial ---

    @property
    def in_waiting(self):
        with self._lock:
            return len(self._rx_buffer)

    def read(self, size=1):
        with self._lock:
            data = bytes(self._rx_buffer[:size])
            del self._rx_buffer[:size]
            return data

    def write(self, data):
        self._process_command(data)
        return len(data)

    def flush(self):
        pass

    def close(self):
        self._running = False
        self._acquisition = False

    def reset_input_buffer(self):
        with self._lock:
            self._rx_buffer.clear()

    def reset_output_buffer(self):
        pass

    # --- Traitement des commandes reçues du PC ---

    def _process_command(self, data):
        if not data:
            return

        i = 0
        while i < len(data):
            cmd = chr(data[i])

            if cmd == 'S':
                # Start → répondre ACK 'O', activer l'acquisition
                self._acquisition = True
                with self._lock:
                    self._rx_buffer.extend(b'O')
                i += 1

            elif cmd == 'E':
                # Stop
                self._acquisition = False
                i += 1

            elif cmd == 'I':
                # Mode identification (on ignore pour le test)
                i += 1

            elif cmd == 'N':
                # Mode normal
                i += 1

            elif cmd == 'P':
                # PWM : 1 octet suivant (0-100)
                if i + 1 < len(data):
                    self._pwm = data[i + 1]
                    i += 2
                else:
                    i += 1

            elif cmd == 'R':
                # Consigne position : 2 octets little-endian
                if i + 2 < len(data):
                    ref = data[i + 1] | (data[i + 2] << 8)
                    self._position_base = ref
                    i += 3
                else:
                    i += 1

            elif cmd == 'G':
                # PID position : 12 octets (3 floats)
                i += 1 + 12

            elif cmd == 'H':
                # PID courant : 8 octets (2 floats)
                i += 1 + 8

            else:
                i += 1

    # --- Génération des paquets simulés ---

    def _packet_sender(self):
        """Envoie des paquets 'T' à ~50 Hz quand l'acquisition est active,
        et des paquets 'T' à ~10 Hz même en idle (comme le firmware fait
        dans loop() avec toggleCounter % 10)."""

        counter = 0
        while self._running:
            # Le firmware envoie toujours des 'T' dans loop(), pas seulement
            # quand acquisitionActive. On simule la même chose.
            pos = self._position_base + random.randint(-3, 3)
            cur = self._courant_base + self._masse_offset + random.randint(-5, 5)

            # Limiter aux bornes ADC 10 bits
            pos = max(0, min(1023, pos))
            cur = max(0, min(1023, cur))

            # Simuler la commande position/courant
            cmd_pos = 512 + random.randint(-2, 2)
            cmd_cur = 512 + random.randint(-2, 2)

            packet = b'T' + struct.pack('<HHHH', pos, cur, cmd_pos, cmd_cur)

            with self._lock:
                self._rx_buffer.extend(packet)

            counter += 1
            # ~50 Hz dans loop() (toggleCounter % 10 à ~500 iter/s)
            time.sleep(0.02)

    # --- Méthodes pour simuler des masses ---

    def simulate_add_mass(self, offset):
        """Simule l'ajout d'une masse (décale le courant)."""
        self._masse_offset = offset

    def simulate_remove_mass(self):
        """Simule le retrait de la masse."""
        self._masse_offset = 0
