import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
# ===== DÉBUT MODIFICATION TEST — import fake serial =====
# import serial                      # ← désactivé pour le test
import struct
from fake_serial import FakeSerial    # ← simulateur Arduino
# ===== FIN MODIFICATION TEST — import fake serial =====
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

BAUDRATE = 115200


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Balance Asservie — MODE TEST (sans Arduino)")
        self.root.geometry("520x560")

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

        # ===== DÉBUT AJOUT CALIBRATION — variables d'état =====
        self.calib_running = False
        self.calib_num_masses = 0
        self.calib_adc_bits = 10
        self.calib_index = 0
        self.calib_masses_real = []
        self.calib_courant_raw = []
        self.calib_data_start_idx = 0
        self.calib_courantRef = 0.0
        self.calib_window = None
        self.calib_results = []
        self.calib_raw_values = []
        # ===== FIN AJOUT CALIBRATION — variables d'état =====

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

        # ===== DÉBUT MODIFICATION TEST — indicateur mode test =====
        ttk.Label(conn, text="  (SIMULÉ)", foreground="red",
                  font=("Arial", 9, "bold")).pack(side="left")
        # ===== FIN MODIFICATION TEST — indicateur mode test =====

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

        # ===== DÉBUT AJOUT CALIBRATION — section UI principale =====
        calib_frame = ttk.LabelFrame(main, text="Calibration", padding=10)
        calib_frame.pack(fill="x", pady=5)

        row1 = ttk.Frame(calib_frame)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="Nombre de masses :").pack(side="left")
        self.calib_num_entry = ttk.Entry(row1, width=5)
        self.calib_num_entry.insert(0, "3")
        self.calib_num_entry.pack(side="left", padx=5)

        row2 = ttk.Frame(calib_frame)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="Bits ADC :").pack(side="left")
        self.calib_bits_entry = ttk.Entry(row2, width=5)
        self.calib_bits_entry.insert(0, "10")
        self.calib_bits_entry.pack(side="left", padx=5)

        ttk.Button(calib_frame, text="Lancer la calibration",
                   command=self.calib_start).pack(pady=5)

        self.calib_results_frame = ttk.Frame(calib_frame)
        self.calib_results_frame.pack(fill="x", pady=2)
        self.calib_results_label = ttk.Label(self.calib_results_frame,
                                             text="Aucune calibration effectuée.",
                                             font=("Arial", 9))
        self.calib_results_label.pack(anchor="w")
        # ===== FIN AJOUT CALIBRATION — section UI principale =====

        # ===== DÉBUT MODIFICATION TEST — boutons simulation masse =====
        sim_frame = ttk.LabelFrame(main, text="Simulation masse (TEST)", padding=10)
        sim_frame.pack(fill="x", pady=5)

        ttk.Label(sim_frame, text="Décalage courant :").pack(side="left")
        self.sim_offset_entry = ttk.Entry(sim_frame, width=6)
        self.sim_offset_entry.insert(0, "30")
        self.sim_offset_entry.pack(side="left", padx=5)

        ttk.Button(sim_frame, text="Ajouter masse",
                   command=self._sim_add_mass).pack(side="left", padx=3)
        ttk.Button(sim_frame, text="Retirer masse",
                   command=self._sim_remove_mass).pack(side="left", padx=3)
        # ===== FIN MODIFICATION TEST — boutons simulation masse =====

    # ===== DÉBUT MODIFICATION TEST — simulation masse =====
    def _sim_add_mass(self):
        """Simule l'ajout d'une masse (décale le courant du simulateur)."""
        if self.ser and isinstance(self.ser, FakeSerial):
            try:
                offset = int(self.sim_offset_entry.get())
            except ValueError:
                offset = 30
            self.ser.simulate_add_mass(offset)

    def _sim_remove_mass(self):
        """Simule le retrait de la masse."""
        if self.ser and isinstance(self.ser, FakeSerial):
            self.ser.simulate_remove_mass()
    # ===== FIN MODIFICATION TEST — simulation masse =====

    # ================= SERIAL =================
    def connect(self):
        # ===== DÉBUT MODIFICATION TEST — connexion simulée =====
        self.ser = FakeSerial(self.port.get(), BAUDRATE)
        # Pas besoin d'attendre 2s pour le boot Arduino
        time.sleep(0.1)
        # ===== FIN MODIFICATION TEST — connexion simulée =====
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

    # ===== DÉBUT AJOUT CALIBRATION — méthodes =====

    def calib_start(self):
        if not self.ser:
            messagebox.showerror("Erreur", "Pas de connexion série.")
            return

        if self.calib_running:
            messagebox.showwarning("Attention", "Calibration déjà en cours.")
            return

        try:
            self.calib_num_masses = int(self.calib_num_entry.get())
            self.calib_adc_bits = int(self.calib_bits_entry.get())
        except ValueError:
            messagebox.showerror("Erreur", "Nombre de masses et bits ADC doivent être des entiers.")
            return

        if self.calib_num_masses < 1:
            messagebox.showerror("Erreur", "Il faut au moins 1 masse de calibration.")
            return

        nb_tare = min(100, len(self.data))
        if nb_tare < 10:
            messagebox.showerror("Erreur",
                                 "Pas assez de données pour le tare de calibration.\n"
                                 "Assurez-vous que la connexion série est active et "
                                 "attendez quelques secondes.")
            return

        recent_data = self.data[-nb_tare:]
        self.calib_courantRef = sum(d[2] for d in recent_data) / len(recent_data)

        self.calib_index = 0
        self.calib_masses_real = [0.0] * self.calib_num_masses
        self.calib_courant_raw = [0.0] * self.calib_num_masses
        self.calib_running = True

        self.calib_data_start_idx = len(self.data)

        self._open_calib_window()

    def _open_calib_window(self):
        if self.calib_window is not None:
            self.calib_window.destroy()

        self.calib_window = tk.Toplevel(self.root)
        self.calib_window.title("Calibration en cours")
        self.calib_window.geometry("400x250")
        self.calib_window.resizable(False, False)
        self.calib_window.protocol("WM_DELETE_WINDOW", self.calib_stop)

        frame = ttk.Frame(self.calib_window, padding=15)
        frame.pack(fill="both", expand=True)

        self.calib_lbl_masse_num = ttk.Label(
            frame,
            text=f"Masse 1 / {self.calib_num_masses}",
            font=("Arial", 14, "bold")
        )
        self.calib_lbl_masse_num.pack(pady=10)

        ttk.Label(frame,
                  text="Placez la masse sur la balance, puis entrez sa valeur réelle."
                  ).pack()

        entry_frame = ttk.Frame(frame)
        entry_frame.pack(pady=10)
        ttk.Label(entry_frame, text="Masse réelle (g) :").pack(side="left")
        self.calib_masse_entry = ttk.Entry(entry_frame, width=10)
        self.calib_masse_entry.pack(side="left", padx=5)
        self.calib_masse_entry.insert(0, "0")

        self.calib_lbl_status = ttk.Label(frame, text="Acquisition en cours...",
                                          foreground="green")
        self.calib_lbl_status.pack(pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=15)

        self.calib_btn_prev = ttk.Button(btn_frame, text="Previous",
                                         command=self.calib_previous)
        self.calib_btn_prev.grid(row=0, column=0, padx=5)

        self.calib_btn_next = ttk.Button(btn_frame, text="Next",
                                         command=self.calib_next)
        self.calib_btn_next.grid(row=0, column=1, padx=5)

        self.calib_btn_stop = ttk.Button(btn_frame, text="Stop",
                                         command=self.calib_stop)
        self.calib_btn_stop.grid(row=0, column=2, padx=5)

        self.calib_btn_prev.config(state="disabled")

        if self.calib_num_masses == 1:
            self.calib_btn_next.config(text="End")

    def _update_calib_window(self):
        if self.calib_window is None:
            return

        idx = self.calib_index
        total = self.calib_num_masses

        self.calib_lbl_masse_num.config(text=f"Masse {idx + 1} / {total}")

        if idx == 0:
            self.calib_btn_prev.config(state="disabled")
        else:
            self.calib_btn_prev.config(state="normal")

        if idx >= total - 1:
            self.calib_btn_next.config(text="End")
        else:
            self.calib_btn_next.config(text="Next")

        self.calib_masse_entry.delete(0, tk.END)
        self.calib_masse_entry.insert(0, str(self.calib_masses_real[idx]))

        self.calib_lbl_status.config(text="Acquisition en cours...", foreground="green")

    def calib_next(self):
        if not self.calib_running:
            return

        try:
            masse_val = float(self.calib_masse_entry.get())
        except ValueError:
            messagebox.showerror("Erreur", "Entrez une valeur numérique pour la masse.")
            return

        current_data = self.data[self.calib_data_start_idx:]
        if len(current_data) < 5:
            messagebox.showwarning("Attention",
                                   "Pas assez d'échantillons. Attendez quelques secondes.")
            return

        courant_moyen = sum(d[2] for d in current_data) / len(current_data)

        self.calib_masses_real[self.calib_index] = masse_val
        self.calib_courant_raw[self.calib_index] = courant_moyen

        if self.calib_index >= self.calib_num_masses - 1:
            self._calib_finish()
        else:
            self.calib_index += 1
            self.calib_data_start_idx = len(self.data)
            self._update_calib_window()

    def calib_previous(self):
        if not self.calib_running or self.calib_index <= 0:
            return

        self.calib_index -= 1
        self.calib_data_start_idx = len(self.data)
        self._update_calib_window()

    def calib_stop(self):
        self.calib_running = False
        if self.calib_window is not None:
            self.calib_window.destroy()
            self.calib_window = None
        messagebox.showinfo("Calibration", "Calibration annulée.")

    def _calib_finish(self):
        self.calib_running = False

        if self.calib_window is not None:
            self.calib_window.destroy()
            self.calib_window = None

        adc_max = (2 ** self.calib_adc_bits) - 1
        plage_courant = 3.0

        self.calib_results = []
        self.calib_raw_values = []

        for i in range(self.calib_num_masses):
            raw = self.calib_courant_raw[i]
            delta_raw = raw - self.calib_courantRef
            courant_A = delta_raw * plage_courant / adc_max

            self.calib_results.append({
                "num": i + 1,
                "masse": self.calib_masses_real[i],
                "courant_A": courant_A,
            })
            self.calib_raw_values.append({
                "num": i + 1,
                "masse": self.calib_masses_real[i],
                "courant_raw": raw,
                "courant_ref": self.calib_courantRef,
                "delta_raw": delta_raw,
            })

        self._display_calib_results()
        messagebox.showinfo("Calibration", "Calibration terminée avec succès !")

    def _display_calib_results(self):
        for widget in self.calib_results_frame.winfo_children():
            widget.destroy()

        header = ttk.Label(self.calib_results_frame,
                           text="Résultats de calibration :",
                           font=("Arial", 10, "bold"))
        header.pack(anchor="w", pady=(5, 2))

        table = ttk.Frame(self.calib_results_frame)
        table.pack(fill="x")

        ttk.Label(table, text="#", width=4, font=("Arial", 9, "bold")).grid(
            row=0, column=0, padx=2)
        ttk.Label(table, text="Masse (g)", width=12, font=("Arial", 9, "bold")).grid(
            row=0, column=1, padx=2)
        ttk.Label(table, text="Courant (A)", width=14, font=("Arial", 9, "bold")).grid(
            row=0, column=2, padx=2)

        for i, res in enumerate(self.calib_results):
            ttk.Label(table, text=str(res["num"]), width=4).grid(
                row=i + 1, column=0, padx=2)
            ttk.Label(table, text=f"{res['masse']:.2f}", width=12).grid(
                row=i + 1, column=1, padx=2)
            ttk.Label(table, text=f"{res['courant_A']:.6f}", width=14).grid(
                row=i + 1, column=2, padx=2)

    def get_calib_raw_values(self):
        return self.calib_raw_values

    # ===== FIN AJOUT CALIBRATION — méthodes =====

    # ================= CLEAN EXIT =================
    def on_close(self):
        self.running = False
        self.plot_running = False

        # ===== DÉBUT AJOUT CALIBRATION — nettoyage =====
        self.calib_running = False
        if self.calib_window is not None:
            try:
                self.calib_window.destroy()
            except:
                pass
        # ===== FIN AJOUT CALIBRATION — nettoyage =====

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
