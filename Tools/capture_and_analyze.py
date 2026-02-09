import serial
import struct
import matplotlib.pyplot as plt
import numpy as np
import time

PORT = 'COM4'      # adapte
BAUD = 115200
N_SAMPLES = 2000

print("Ouverture du port série...")
ser = serial.Serial(PORT, BAUD, timeout=1)
print("Port série ouvert")

# start acquisition
time.sleep(2)
ser.write(b'S')

data = []

while len(data) < N_SAMPLES:
    print("waiting")
    raw = ser.read(2)
    print(raw)
    if len(raw) == 2:
        value = struct.unpack('<H', raw)[0]
        data.append(value)
        print(len(data))

# stop acquisition
ser.write(b'E')
ser.close()

# plot
plt.plot(data)
plt.xlabel("Sample")
plt.ylabel("ADC value")
plt.title("ADC acquisition")
plt.grid()
plt.show()
