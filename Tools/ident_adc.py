import serial
import time
import struct
import matplotlib.pyplot as plt
import threading

# ===== CONFIG =====
PORT = "COM4"
BAUD = 115200

ser = serial.Serial(PORT, BAUD, timeout=1)
data = []

def read_data():
    while True:
        if ser.read(1) == b'T':
            raw = ser.read(9)
            if len(raw) == 9:
                pos, cur, cmd_pos, cmd_cur, valid = struct.unpack('<HHHHB', raw)
                data.append((pos, cur))

# ===== START THREAD =====
threading.Thread(target=read_data, daemon=True).start()

time.sleep(2)

# ===== START acquisition =====
ser.write(b'N')  # mode asservi
time.sleep(0.1)

ser.write(b'S')
print("Acquisition démarrée")

# ===== TEMPS D'ACQUISITION =====
time.sleep(0.00001)

# ===== STOP =====
ser.write(b'E')
time.sleep(0.1)

all_data = list(data)
if len(all_data) == 0:
    raise Exception("Aucune donnée reçue")

# ===== EXTRACTION =====
pos = [d[0] for d in all_data]   # A0
cur = [d[1] for d in all_data]   # A1
samples = list(range(len(all_data)))  # axe x = index

# ===== PLOT =====
plt.figure()

plt.plot(samples, pos, label="A0 (Position)")
plt.plot(samples, cur, label="A1 (Courant)")

plt.xlabel("Samples")
plt.ylabel("ADC value")
plt.title("A0 et A1")
plt.legend()
plt.grid()

plt.tight_layout()
plt.savefig("ADC_plot.png", dpi=150)
print("PNG sauvegardé: ADC_plot.png")

plt.show()