import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import serial
import struct
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

BAUDRATE = 115200


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Balance Asservie")
        self.root.geometry("520x520")

        style = ttk.Style()
        style.theme_use("clam")

        self.ser = None
        self.rx_buffer = bytearray()

        self.running = False
        self.plot_running = False

        self.last_courant = 0
        self.last_flag = 0
        self.offset = 0

        self.data = []

        self.fig = None

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
        while len(self.rx_buffer) >= 1:
            cmd = self.rx_buffer[0]

            if cmd == ord('M'):
                if len(self.rx_buffer) < 4:
                    return
                cur = self.rx_buffer[1] | (self.rx_buffer[2] << 8)
                flag = self.rx_buffer[3]
                del self.rx_buffer[:4]

                self.last_courant = cur
                self.last_flag = flag

                self.masse.set(f"{cur - self.offset}")
                self.canvas.itemconfig(self.led, fill="green" if flag else "red")

            elif cmd == ord('T'):
                if len(self.rx_buffer) < 9:
                    return

                pos, cur, cmd_pos, cmd_cur = struct.unpack('<HHHH', self.rx_buffer[1:9])
                del self.rx_buffer[:9]

                self.data.append((time.time(), pos, cur, cmd_pos, cmd_cur))

            else:
                del self.rx_buffer[0]

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
        if self.last_flag:
            self.offset = self.last_courant
        else:
            messagebox.showerror("Erreur", "Instable")

    # ================= START / STOP =================
    def start(self):
        if self.running:
            print("Déjà en cours")
            return

        self.running = True
        self.data.clear()

        self.start_plot()

        pwm = int(self.pwm_entry.get())

        if self.mode.get() == "identification":
            self.send(b'I')

            if self.signal_type.get() == "step":
                self.send(b'P' + bytes([pwm]))

            elif self.signal_type.get() == "pulse":
                self.send(b'P' + bytes([pwm]))
                time.sleep(0.05)
                self.send(b'P' + bytes([50]))
        else:
            self.send(b'N')

        self.send(b'S')

    def stop(self):
        if not self.running:
            return

        self.running = False
        self.send(b'E')
        self.send(b'P' + bytes([50]))

    # ================= GRAPH =================
    def start_plot(self):
        if self.fig:
            plt.close(self.fig)

        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1)

        self.line_cur, = self.ax1.plot([], [], label="Courant")
        self.line_pos, = self.ax1.plot([], [], label="Position")

        self.line_cmd_pos, = self.ax2.plot([], [], label="Cmd Position")
        self.line_cmd_cur, = self.ax2.plot([], [], label="Cmd Courant")

        self.ax1.legend()
        self.ax2.legend()

        self.plot_running = True
        threading.Thread(target=self.update_plot_loop, daemon=True).start()

        plt.show(block=False)

    def update_plot_loop(self):
        while self.plot_running:
            if len(self.data) > 2:
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

                self.ax1.relim()
                self.ax1.autoscale_view()
                self.ax2.relim()
                self.ax2.autoscale_view()

                self.fig.canvas.draw()
                self.fig.canvas.flush_events()

            time.sleep(0.1)

    # ================= CLEAN EXIT =================
    def on_close(self):
        self.running = False
        self.plot_running = False
        if self.ser:
            try:
                self.send(b'E')
                self.send(b'P' + bytes([50]))
                self.ser.close()
            except:
                pass
        self.root.destroy()


# ================= MAIN =================
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()