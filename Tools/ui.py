import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import serial

BAUDRATE = 115200


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Interface Identification / Asservissement")

        self.ser = None
        self.rx_buffer = bytearray()
        self.running = False

        self.create_widgets()

    # ==========================
    # UI
    # ==========================
    def create_widgets(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")

        # PORT
        ttk.Label(frame, text="Port série:").grid(row=0, column=0, sticky="w")
        self.port_entry = ttk.Entry(frame, width=20)
        self.port_entry.grid(row=0, column=1)
        self.port_entry.insert(0, "COM3")

        ttk.Button(frame, text="Connecter", command=self.connect_serial).grid(row=0, column=2)

        # MODE
        ttk.Label(frame, text="Mode:").grid(row=1, column=0, sticky="w")
        self.mode = tk.StringVar(value="normal")

        ttk.Radiobutton(frame, text="Asservi (boucle fermée)", variable=self.mode, value="normal").grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(frame, text="Identification (boucle ouverte)", variable=self.mode, value="identification").grid(row=2, column=1, sticky="w")

        # SIGNAL
        ttk.Label(frame, text="Signal:").grid(row=3, column=0, sticky="w")
        self.signal_type = tk.StringVar(value="step")

        ttk.Radiobutton(frame, text="Échelon", variable=self.signal_type, value="step").grid(row=3, column=1, sticky="w")
        ttk.Radiobutton(frame, text="Impulsion", variable=self.signal_type, value="pulse").grid(row=4, column=1, sticky="w")

        # PWM
        ttk.Label(frame, text="PWM (%):").grid(row=5, column=0, sticky="w")
        self.pwm_entry = ttk.Entry(frame, width=10)
        self.pwm_entry.grid(row=5, column=1)
        self.pwm_entry.insert(0, "50")

        # BOUTONS
        ttk.Button(frame, text="Lancer test", command=self.start_test_thread).grid(row=6, column=0, columnspan=3, pady=10)
        ttk.Button(frame, text="Stop", command=self.stop_system).grid(row=7, column=0, columnspan=3)

        # STATUS
        self.status = tk.StringVar(value="Non connecté")
        ttk.Label(frame, textvariable=self.status).grid(row=8, column=0, columnspan=3)

        # COURANT LIVE
        ttk.Label(frame, text="Masse:").grid(row=9, column=0, sticky="w")
        self.masse = tk.StringVar(value="---")
        ttk.Label(frame, textvariable=self.masse).grid(row=9, column=1)

    # ==========================
    # SERIAL
    # ==========================
    def connect_serial(self):
        port = self.port_entry.get()
        try:
            self.ser = serial.Serial(port=port, baudrate=BAUDRATE, timeout=0)
            time.sleep(2)
            self.ser.reset_input_buffer()

            self.start_reader_thread()

            self.status.set(f"Connecté à {port}")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def send_cmd(self, cmd: bytes):
        if self.ser:
            self.ser.write(cmd)
            self.ser.flush()

    def send_pwm(self, pwm: int):
        if self.ser:
            self.ser.write(bytes((ord('P'), pwm)))
            self.ser.flush()

    # ==========================
    # THREAD LECTURE
    # ==========================
    def start_reader_thread(self):
        self.running = True
        thread = threading.Thread(target=self.serial_reader)
        thread.daemon = True
        thread.start()

    def serial_reader(self):
        while self.running and self.ser:
            try:
                if self.ser.in_waiting:
                    data = self.ser.read(self.ser.in_waiting)
                    self.rx_buffer.extend(data)
                    self.parse_buffer()

                time.sleep(0.001)

            except Exception as e:
                print("Erreur lecture:", e)
                break

    def parse_buffer(self):
        while len(self.rx_buffer) >= 1:
            cmd = self.rx_buffer[0]

            # ===== LIVE =====
            if cmd == ord('M'):
                if len(self.rx_buffer) < 4:
                    return

                courant = self.rx_buffer[1] | (self.rx_buffer[2] << 8)
                flag = self.rx_buffer[3]

                del self.rx_buffer[:4]

                if flag == 1:
                    self.masse.set(f"{courant}")
                else:
                    self.masse.set("...")

            # ===== IDENTIFICATION =====
            elif cmd == ord('D'):
                if len(self.rx_buffer) < 5:
                    return

                pos = self.rx_buffer[1] | (self.rx_buffer[2] << 8)
                cur = self.rx_buffer[3] | (self.rx_buffer[4] << 8)

                del self.rx_buffer[:5]

                # Ici tu peux stocker les données
                # print(f"D: pos={pos}, cur={cur}")

            else:
                del self.rx_buffer[0]

    # ==========================
    # CONTROLE SYSTEME
    # ==========================
    def configure_mode(self):
        if self.mode.get() == "identification":
            self.send_cmd(b'I')
            self.status.set("Mode identification (boucle ouverte)")
        else:
            self.send_cmd(b'N')
            self.status.set("Mode asservi (boucle fermée)")

    def stop_system(self):
        if self.ser:
            self.send_cmd(b'E')
            self.send_pwm(50)
            self.running = False
            self.status.set("Arrêt")

    # ==========================
    # TEST
    # ==========================
    def start_test_thread(self):
        if self.ser is None:
            messagebox.showwarning("Attention", "Pas connecté")
            return

        thread = threading.Thread(target=self.run_test)
        thread.start()

    def run_test(self):
        try:
            pwm = int(self.pwm_entry.get())
            signal = self.signal_type.get()

            self.configure_mode()

            self.send_cmd(b'S')
            time.sleep(0.1)

            self.status.set("Test en cours...")

            if signal == "step":
                self.send_pwm(pwm)
                time.sleep(5)

            elif signal == "pulse":
                self.send_pwm(pwm)
                time.sleep(0.05)
                self.send_pwm(50)
                time.sleep(5)

            self.send_cmd(b'E')
            self.send_pwm(50)

            self.status.set("Test terminé")

        except Exception as e:
            messagebox.showerror("Erreur", str(e))
            self.status.set("Erreur")


# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()