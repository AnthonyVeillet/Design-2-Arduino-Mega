import serial
import time
import struct
import csv
import matplotlib.pyplot as plt
import threading

# ===== CONFIG =====
PORT = "COM4"        # <-- à adapter
BAUD = 115200

MODE = "asservi"     # "impulse" ou "step" ou "asservi"
PWM = 70             # 0–100
DURATION_MS = 50     # seulement pour impulsion

REF_TIME = 5
STEP_TIME = 5000
POST_TIME = 10

# ==================

ser = serial.Serial(PORT, BAUD, timeout=1)
data = []

def read_data():
    while True:
        if ser.read(1) == b'T':
            raw = ser.read(9)  # 2+2+2+2+1
            if len(raw) == 9:
                pos, cur, cmd_pos, cmd_cur, valid = struct.unpack('<HHHHB', raw)
                data.append((time.time(), pos, cur, cmd_pos, cmd_cur))

# ===== START THREAD =====
threading.Thread(target=read_data, daemon=True).start()

time.sleep(2)  # laisser Arduino démarrer

# ===== INIT =====
if MODE != "asservi":
    ser.write(b'I')
else:
    ser.write(b'N')
# ser.write(b'P' + bytes([50]))
time.sleep(0.1)

# START acquisition
ser.write(b'S')
ack = ser.read(1)
# if ack != b'O':
#     raise Exception("ACK non reçu")

print("Acquisition démarrée")

# ===== PHASE TEST =====
if MODE == "impulse":
    print("Impulsion")
    ser.write(b'U' + bytes([PWM]) + DURATION_MS.to_bytes(2, 'little'))
    time.sleep((DURATION_MS / 1000.0) + POST_TIME)

elif MODE == "step":
    print("Échelon")
    ser.write(b'U' + bytes([PWM]) + STEP_TIME.to_bytes(2, 'little'))
    time.sleep((STEP_TIME / 1000.0) + POST_TIME)

else:
    print("Asservi")
    time.sleep(5)


# ===== STOP =====
ser.write(b'E')
time.sleep(1)

all_data = list(data)
if len(all_data) == 0:
    raise Exception("Aucune donnée reçue")

# ===== CSV =====
# filename = f"{MODE}_{PWM}.csv"
filename = f"reg_pos.csv"
with open(filename, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["time", "pos", "cur", "cmd_pos", "cmd_cur"])
    t0 = all_data[0][0]
    for d in all_data:
        writer.writerow([
            d[0] - t0,  # temps relatif
            d[1],       # position
            d[2],       # courant
            d[3],       # commande position
            d[4]        # commande courant
        ])

print("CSV sauvegardé:", filename)

# ===== PLOT =====
t = [d[0] - all_data[0][0] for d in all_data]
pos = [d[1] for d in all_data]
cur = [d[2] for d in all_data]
cmd_pos = [d[3] for d in all_data]
cmd_cur = [d[4] for d in all_data]

plt.figure()

# ===== POSITION =====
plt.subplot(2, 1, 1)
plt.plot(t, pos, label="Position réelle")
plt.plot(t, cmd_pos, '--', label="Commande position")
plt.title("Position")
plt.legend()
plt.grid()

# ===== COURANT =====
plt.subplot(2, 1, 2)
plt.plot(t, cur, label="Courant réel")
plt.plot(t, cmd_cur, '--', label="Commande courant")
plt.title("Courant")
plt.legend()
plt.grid()

plt.tight_layout()

# png = f"{MODE}_{PWM}.png"
png = "reg_pos.png"
plt.savefig(png, dpi=150)
print("PNG sauvegardé:", png)

plt.show()