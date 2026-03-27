from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import serial
import struct
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import csv
from pathlib import Path

BAUDRATE = 115200
WINDOW_TIME = 10


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Balance Asservie")
        self.root.geometry("520x520")

        self.ser = None
        self.rx_buffer = bytearray()

        self.running = False
        self.plot_running = False
        self.ident_running = False

        self.last_courant = 0
        self.last_flag = 0
        self.offset = 0

        self.data = []

        self.fig = None

        self.data_dir = Path("dataIdentification")
        self.data_dir.mkdir(exist_ok=True)

        self.create_widgets()

    # ================= UI =================
    def create_widgets(self):
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill="both", expand=True)

        conn = ttk.LabelFrame(main, text="Connexion", padding=10)
        conn.pack(fill="x", pady=5)

        self.port = ttk.Entry(conn, width=10)
        self.port.insert(0, "COM4")
        self.port.pack(side="left", padx=5)

        ttk.Button(conn, text="Connecter", command=self.connect).pack(side="left")

        mode_frame = ttk.LabelFrame(main, text="Mode", padding=10)
        mode_frame.pack(fill="x", pady=5)

        self.mode = tk.StringVar(value="normal")
        ttk.Radiobutton(mode_frame, text="Asservi", variable=self.mode, value="normal").pack(side="left", padx=10)
        ttk.Radiobutton(mode_frame, text="Identification", variable=self.mode, value="identification").pack(side="left")

        ident_frame = ttk.LabelFrame(main, text="Identification", padding=10)
        ident_frame.pack(fill="x", pady=5)

        self.signal_type = tk.StringVar(value="step")
        ttk.Radiobutton(ident_frame, text="Échelon", variable=self.signal_type, value="step").pack(side="left", padx=10)
        ttk.Radiobutton(ident_frame, text="Impulsion", variable=self.signal_type, value="pulse").pack(side="left")

        ttk.Label(ident_frame, text="PWM (%)").pack(side="left", padx=10)
        self.pwm_entry = ttk.Entry(ident_frame, width=5)
        self.pwm_entry.insert(0, "50")
        self.pwm_entry.pack(side="left")

        ref_frame = ttk.LabelFrame(main, text="Position de référence", padding=10)
        ref_frame.pack(fill="x", pady=5)

        self.pos_ref = ttk.Entry(ref_frame, width=10)
        self.pos_ref.insert(0, "430")
        self.pos_ref.pack(side="left", padx=5)

        ttk.Button(ref_frame, text="Envoyer", command=self.send_ref).pack(side="left")

        pid_frame = ttk.LabelFrame(main, text="Régulateurs", padding=10)
        pid_frame.pack(fill="x", pady=5)

        ttk.Label(pid_frame, text="Position (Kp Ki Kd)").grid(row=0, column=0)

        self.kp = ttk.Entry(pid_frame, width=5)
        self.ki = ttk.Entry(pid_frame, width=5)
        self.kd = ttk.Entry(pid_frame, width=5)

        self.kp.insert(0, "1")
        self.ki.insert(0, "0")
        self.kd.insert(0, "0")

        self.kp.grid(row=0, column=1)
        self.ki.grid(row=0, column=2)
        self.kd.grid(row=0, column=3)

        ttk.Button(pid_frame, text="Appliquer", command=self.send_pid_pos).grid(row=0, column=4)

        ttk.Label(pid_frame, text="Courant (Kp Ki)").grid(row=1, column=0)

        self.kp_c = ttk.Entry(pid_frame, width=5)
        self.ki_c = ttk.Entry(pid_frame, width=5)

        self.kp_c.insert(0, "1")
        self.ki_c.insert(0, "0")

        self.kp_c.grid(row=1, column=1)
        self.ki_c.grid(row=1, column=2)

        ttk.Button(pid_frame, text="Appliquer", command=self.send_pid_cur).grid(row=1, column=4)

        measure_frame = ttk.LabelFrame(main, text="Mesure", padding=10)
        measure_frame.pack(fill="x", pady=5)

        ttk.Label(measure_frame, text="Masse:").pack(side="left")

        self.masse = tk.StringVar(value="---")
        ttk.Label(measure_frame, textvariable=self.masse, font=("Arial", 14, "bold")).pack(side="left", padx=10)

        self.canvas = tk.Canvas(measure_frame, width=20, height=20)
        self.canvas.pack(side="left", padx=10)
        self.led = self.canvas.create_oval(2, 2, 18, 18, fill="red")

        action = ttk.Frame(main)
        action.pack(pady=10)

        ttk.Button(action, text="Start", command=self.start).grid(row=0, column=0, padx=5)
        ttk.Button(action, text="Stop", command=self.stop).grid(row=0, column=1, padx=5)
        ttk.Button(action, text="Tare", command=self.tare).grid(row=0, column=2, padx=5)
        ttk.Button(action, text="Identification complète", command=self.run_identification).grid(row=0, column=3, padx=5)

    # ================= SERIAL =================
    def connect(self):
        self.ser = serial.Serial(self.port.get(), BAUDRATE, timeout=0)
        time.sleep(2)
        threading.Thread(target=self.reader, daemon=True).start()

    def reader(self):
        while True:
            if self.ser and self.ser.in_waiting:
                self.rx_buffer.extend(self.ser.read(self.ser.in_waiting))
                self.parse()
            time.sleep(0.001)

    def parse(self):
        while len(self.rx_buffer) >= 10:
            if self.rx_buffer[0] != ord('T'):
                del self.rx_buffer[0]
                continue

            pos, cur, cmd_pos, cmd_cur = struct.unpack('<HHHH', self.rx_buffer[1:9])
            flag = self.rx_buffer[9]

            del self.rx_buffer[:10]

            self.last_courant = cur
            self.last_flag = flag

            self.masse.set(f"{cur - self.offset}")

            if flag:
                self.canvas.itemconfig(self.led, fill="green")
            else:
                self.canvas.itemconfig(self.led, fill="red")

            self.data.append((time.time(), pos, cur, cmd_pos, cmd_cur))

    # ================= COMMANDES =================
    def send(self, b):
        if self.ser:
            self.ser.write(b)

    def send_ref(self):
        self.send(b'R' + struct.pack('<H', int(self.pos_ref.get())))

    def send_pid_pos(self):
        self.send(b'G' + struct.pack('<fff',
                                     float(self.kp.get()),
                                     float(self.ki.get()),
                                     float(self.kd.get())))

    def send_pid_cur(self):
        self.send(b'H' + struct.pack('<ff',
                                     float(self.kp_c.get()),
                                     float(self.ki_c.get())))

    def tare(self):
        self.offset = self.last_courant

    # ================= START / STOP =================
    def start(self):
        self.running = True
        self.data.clear()

        pwm = int(self.pwm_entry.get())

        if self.mode.get() == "identification":
            self.send(b'I')
            self.send(b'P' + bytes([pwm]))
        else:
            self.send(b'N')

        self.send(b'S')
        self.start_plot()

    def stop(self):
        self.running = False
        self.plot_running = False
        self.send(b'E')
        self.send(b'P' + bytes([50]))

    # ================= IDENTIFICATION =================
    def run_identification(self):
        if not self.ser:
            messagebox.showerror("Erreur", "Pas connecté")
            return

        if self.ident_running:
            return

        self.ident_running = True
        threading.Thread(target=self.ident_thread, daemon=True).start()

    def ident_thread(self):
        try:
            pwm = int(self.pwm_entry.get())
            mode = self.signal_type.get()

            REF_TIME = 5
            STEP_TIME = 15 if mode == "step" else 0.05
            POST_TIME = 15

            self.data.clear()

            self.send(b'I')
            self.send(b'P' + bytes([50]))
            time.sleep(0.1)

            self.send(b'S')

            time.sleep(REF_TIME)
            ref_data = list(self.data)

            pos_ref = sum(d[1] for d in ref_data) / len(ref_data)
            cur_ref = sum(d[2] for d in ref_data) / len(ref_data)

            self.send(b'P' + bytes([pwm]))

            t0 = time.time()
            zero_sent = False

            while True:
                elapsed = time.time() - t0

                if (not zero_sent) and elapsed >= STEP_TIME:
                    self.send(b'P' + bytes([50]))
                    zero_sent = True

                if elapsed >= STEP_TIME + POST_TIME:
                    break

                time.sleep(0.001)

            self.send(b'E')

            all_data = list(self.data)

            filename = self.data_dir / f"{mode}_{pwm}.csv"

            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["time", "pos", "cur", "cmd_pos", "cmd_cur", "pos_reel", "cur_reel"])

                t0 = all_data[0][0]

                for d in all_data:
                    t = d[0] - t0
                    writer.writerow([
                        t, d[1], d[2], d[3], d[4],
                        d[1] - pos_ref,
                        d[2] - cur_ref
                    ])

            print("CSV sauvegardé:", filename)

            t = [d[0] - all_data[0][0] for d in all_data]
            pos = [d[1] - pos_ref for d in all_data]
            cur = [d[2] - cur_ref for d in all_data]

            plt.figure()
            plt.subplot(2,1,1)
            plt.plot(t, pos)
            plt.title("Position réelle")

            plt.subplot(2,1,2)
            plt.plot(t, cur)
            plt.title("Courant réel")

            png = self.data_dir / f"{mode}_{pwm}.png"
            plt.savefig(png)
            print("PNG sauvegardé:", png)

            plt.show()

        except Exception as e:
            print("Erreur identification:", e)

        finally:
            self.ident_running = False

    # ================= OSCILLO =================
    def start_plot(self):
        if self.fig:
            plt.close(self.fig)

        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1)

        self.line_cur, = self.ax1.plot([], [])
        self.line_pos, = self.ax1.plot([], [])

        self.line_cmd_pos, = self.ax2.plot([], [])
        self.line_cmd_cur, = self.ax2.plot([], [])

        self.plot_running = True
        self.update_plot()

        plt.show(block=False)

    def update_plot(self):
        if not self.plot_running:
            return

        if len(self.data) > 2:
            now = time.time()
            self.data = [d for d in self.data if now - d[0] <= WINDOW_TIME]

            t0 = self.data[0][0]

            t = [d[0] - t0 for d in self.data]
            pos = [d[1] for d in self.data]
            cur = [d[2] for d in self.data]
            cmd_pos = [d[3] for d in self.data]
            cmd_cur = [d[4] for d in self.data]

            self.line_cur.set_data(t, cur)
            self.line_pos.set_data(t, pos)
            self.line_cmd_pos.set_data(t, cmd_pos)
            self.line_cmd_cur.set_data(t, cmd_cur)

            self.ax1.set_xlim(max(0, t[-1] - WINDOW_TIME), t[-1])
            self.ax2.set_xlim(max(0, t[-1] - WINDOW_TIME), t[-1])

            self.ax1.relim()
            self.ax1.autoscale_view()
            self.ax2.relim()
            self.ax2.autoscale_view()

            self.fig.canvas.draw_idle()

        self.root.after(50, self.update_plot)

    # ================= EXIT =================
    def on_close(self):
        if self.ser:
            try:
                self.send(b'E')
                self.send(b'P' + bytes([50]))
                self.ser.close()
            except:
                pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()