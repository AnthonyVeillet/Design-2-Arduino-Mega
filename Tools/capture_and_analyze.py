import serial
import struct
import matplotlib.pyplot as plt
import numpy as np
import time

PORT = 'COM4'
BAUD = 115200
N_SAMPLES = 2000

print("Ouverture du port série...")
ser = serial.Serial(PORT, BAUD, timeout=1)
print("Port série ouvert")

time.sleep(2)
ser.write(b'S')

ack = ser.read(1)
print("ACK reçu:", ack)

data_ch0 = []
data_ch1 = []

while len(data_ch0) < N_SAMPLES:
    raw = ser.read(4)   # 4 octets
    if len(raw) == 4:
        ch0, ch1 = struct.unpack('<HH', raw)
        data_ch0.append(ch0)
        data_ch1.append(ch1)
        print(ch0)
        print(ch1)

ser.write(b'E')

while True:
    b = ser.read(1)
    if b == b'K':
        print("ACK stop reçu")
        break

ser.close()

# Plot
plt.plot(data_ch0, label="A0")
plt.plot(data_ch1, label="A1")
plt.xlabel("Sample")
plt.ylabel("ADC value")
plt.title("ADC acquisition - 2 channels")
plt.legend()
plt.grid()
plt.show()
