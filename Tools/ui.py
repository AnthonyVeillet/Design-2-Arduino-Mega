import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import serial
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

BAUDRATE = 115200


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Interface Identification / Asservissement")

        self.ser = None
        self.rx_buffer = bytearray()
        self.running = False

        # LIVE
        self.last_courant = 0
        self.last_flag = 0
        self.offset = 0

        # DATA (robuste)
        self.data = []

        self.create_widgets()

    # ==========================
    # UI
    # ==========================
    def create_widgets(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="Port série:").grid(row=0, column=0)
        self.port_entry = ttk.Entry(frame)
        self.port_entry.grid(row=0, column=1)
        self.port_entry.insert(0, "COM4")

        ttk.Button(frame, text="Connecter", command=self.connect_serial).grid(row=0, column=2)

        self.mode = tk.StringVar(value="normal")
        ttk.Radiobutton(frame, text="Asservi", variable=self.mode, value="normal").grid(row=1, column=1)
        ttk.Radiobutton(frame, text="Identification", variable=self.mode, value="identification").grid(row=2, column=1)

        self.signal_type = tk.StringVar(value="step")
        ttk.Radiobutton(frame, text="Échelon", variable=self.signal_type, value="step").grid(row=3, column=1)
        ttk.Radiobutton(frame, text="Impulsion", variable=self.signal_type, value="pulse").grid(row=4, column=1)

        ttk.Label(frame, text="PWM (%)").grid(row=5, column=0)
        self.pwm_entry = ttk.Entry(frame)
        self.pwm_entry.grid(row=5, column=1)
        self.pwm_entry.insert(0, "50")

        ttk.Button(frame, text="Lancer test", command=self.start_test_thread).grid(row=6, column=0, columnspan=3)
        ttk.Button(frame, text="Stop", command=self.stop_system).grid(row=7, column=0, columnspan=3)

        ttk.Button(frame, text="Tare", command=self.do_tare).grid(row=8, column=0, columnspan=3)

        self.status = tk.StringVar(value="Non connecté")
        ttk.Label(frame, textvariable=self.status).grid(row=9, column=0, columnspan=3)

        ttk.Label(frame, text="Masse:").grid(row=10, column=0)
        self.masse = tk.StringVar(value="---")
        ttk.Label(frame, textvariable=self.masse).grid(row=10, column=1)

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

    def send_pwm(self, pwm: int):
        if self.ser:
            self.ser.write(bytes((ord('P'), pwm)))

    # ==========================
    # THREAD LECTURE
    # ==========================
    def start_reader_thread(self):
        self.running = True
        threading.Thread(target=self.serial_reader, daemon=True).start()

    def serial_reader(self):
        while self.running and self.ser:
            if self.ser.in_waiting:
                data = self.ser.read(self.ser.in_waiting)
                self.rx_buffer.extend(data)
                self.parse_buffer()
            time.sleep(0.001)

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

                self.last_courant = courant
                self.last_flag = flag

                if flag:
                    self.masse.set(f"{courant - self.offset}")
                else:
                    self.masse.set("...")

            # ===== IDENTIFICATION =====
            elif cmd == ord('D'):
                if len(self.rx_buffer) < 5:
                    return

                pos = self.rx_buffer[1] | (self.rx_buffer[2] << 8)
                cur = self.rx_buffer[3] | (self.rx_buffer[4] << 8)
                del self.rx_buffer[:5]

                t = time.time()
                self.data.append((t, pos, cur))  # ✅ STRUCTURE ROBUSTE

            else:
                del self.rx_buffer[0]

    # ==========================
    # TARE
    # ==========================
    def do_tare(self):
        if self.last_flag == 1:
            self.offset = self.last_courant
            messagebox.showinfo("Tare", "Tare effectuée")
        else:
            messagebox.showerror("Erreur", "Balance instable !")

    # ==========================
    # CONTROLE
    # ==========================
    def configure_mode(self):
        if self.mode.get() == "identification":
            self.send_cmd(b'I')
        else:
            self.send_cmd(b'N')

    def stop_system(self):
        if self.ser:
            self.send_cmd(b'E')
            self.send_pwm(50)
            self.running = False

    # ==========================
    # TEST
    # ==========================
    def start_test_thread(self):
        if self.ser is None:
            messagebox.showwarning("Attention", "Pas connecté")
            return

        threading.Thread(target=self.run_test).start()

    def run_test(self):
        try:
            self.data.clear()

            pwm = int(self.pwm_entry.get())
            signal = self.signal_type.get()

            self.configure_mode()

            self.send_cmd(b'S')
            time.sleep(0.1)

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

            self.root.after(0, self.plot_data)

        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    # ==========================
    # PLOT
    # ==========================
    def plot_data(self):
        if len(self.data) < 2:
            messagebox.showwarning("Graphique", "Pas assez de données")
            return

        t0 = self.data[0][0]
        times = [d[0] - t0 for d in self.data]
        pos = [d[1] for d in self.data]
        cur = [d[2] for d in self.data]

        plt.figure()
        plt.plot(times, cur, label="Courant")
        plt.plot(times, pos, label="Position")

        plt.title("Réponse du système")
        plt.xlabel("Temps (s)")
        plt.ylabel("Valeur")
        plt.legend()
        plt.grid()

        plt.show()


# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()