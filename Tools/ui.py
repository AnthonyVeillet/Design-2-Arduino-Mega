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
import winsound
from collections import deque
import statistics
import sys
from tkinter.scrolledtext import ScrolledText

# ===== DÉBUT AJOUT — imports calibration =====
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import masse
# ===== FIN AJOUT — imports calibration =====

# ===== DÉBUT AJOUT — imports simulation =====
import random
import math
# ===== FIN AJOUT — imports simulation =====

BAUDRATE = 115200
WINDOW_TIME = 10
masseRT_affichage = 1000 # Fréquence d'affichage de la masse temps réel (en ms)

# ========== Code pour afficher les prints dans l'app DEBUT
class TextRedirector:
    def __init__(self, app, tag=None):
        self.app = app
        self.tag = tag

    def write(self, text):
        if not text:
            return
        # Toujours repasser par le thread principal Tkinter
        self.app.root.after(0, self.app._append_console, text, self.tag)

    def flush(self):
        pass
# ========== Code pour afficher les prints dans l'app FIN
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Balance Asservie")

        # ===== DÉBUT AJOUT — fenêtre scrollable =====
        self.CONTENT_W = 1800
        self.CONTENT_H = 1000

        # Taille initiale = min(contenu, écran)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        init_w = min(self.CONTENT_W, screen_w - 50)
        init_h = min(self.CONTENT_H, screen_h - 80)
        self.root.geometry(f"{init_w}x{init_h}")
        # ===== FIN AJOUT — fenêtre scrollable =====

        self.ser = None
        self.rx_buffer = bytearray()

        self.running = False
        self.plot_running = False
        self.ident_running = False

        self.last_courant = 0
        self.last_flag = 0
        self.offset = 0
        self.init_tare_flag = True # Pour faire un tare automatique
        self.bouton_tare_flag = False # Permet au bouton Tare d'être actif seulement apres asservissement et moyennage

        self.data = []

        self.fig = None

        self.data_dir = Path("dataIdentification")
        self.data_dir.mkdir(exist_ok=True)

        # ===== DÉBUT AJOUT — variables calibration =====
        self.cal_window = None
        # ===== FIN AJOUT — variables calibration =====

        # ===== DÉBUT AJOUT — variables simulation =====
        self.sim_mode = False
        self.sim_thread = None
        self.sim_running = False
        self.sim_pwm = 50           # PWM courante (50 = 0A = repos)
        self.sim_position = 300.0   # Position simulée (autour de positionRef)
        self.sim_courant = 512.0    # Courant simulé (512 = milieu ADC = 0A)
        self.sim_flag_counter = 0   # Compteur pour simuler la stabilisation
        # ===== FIN AJOUT — variables simulation =====

        # ===== STABILITÉ =====

        self.masse_lock_flag = True # Pour indiquer que la masse lock peut être mise à jour (après asservissement et moyennage)
        self.avg_value = None
        self.avg_value_lock = None
        self.stable = False
        self.stable_since = None

        self.stab_buffer = deque(maxlen=150)
        self.span_threshold = 6.0
        self.std_threshold = 1.5
        self.min_stable_time = 0.5

        # ========== Code pour afficher les prints dans l'app DEBUT
        self._stdout = sys.stdout
        # ========== Code pour afficher les prints dans l'app FIN

        self.create_widgets()

        # ========== Code pour afficher les prints dans l'app DEBUT
        sys.stdout = TextRedirector(self)
        self._append_console("Console intégrée prête.\n")
        # ========== Code pour afficher les prints dans l'app FIN

    # ================= UI =================
    def create_widgets(self):
        # ===== DÉBUT AJOUT — conteneur scrollable =====
        # ========== Code pour afficher les prints dans l'app DEBUT
        root_container = ttk.Frame(self.root)
        root_container.pack(fill="both", expand=True)

        root_container.columnconfigure(0, weight=4)
        root_container.columnconfigure(1, weight=1)
        root_container.rowconfigure(0, weight=1)

        self.left_panel = ttk.Frame(root_container)
        self.left_panel.grid(row=0, column=0, sticky="nsew")

        self.right_panel = ttk.Frame(root_container, padding=(8, 0, 0, 0))
        self.right_panel.grid(row=0, column=1, sticky="nsew")

        # ===== conteneur scrollable à gauche =====
        self.scroll_container = ttk.Frame(self.left_panel)
        self.scroll_container.pack(fill="both", expand=True)

        self.scroll_canvas = tk.Canvas(self.scroll_container, highlightthickness=0)
        self.v_scrollbar = ttk.Scrollbar(
            self.scroll_container,
            orient="vertical",
            command=self.scroll_canvas.yview
        )
        self.h_scrollbar = ttk.Scrollbar(
            self.scroll_container,
            orient="horizontal",
            command=self.scroll_canvas.xview
        )
        self.scroll_canvas.configure(
            yscrollcommand=self.v_scrollbar.set,
            xscrollcommand=self.h_scrollbar.set
        )

        self.h_scrollbar.pack(side="bottom", fill="x")
        self.v_scrollbar.pack(side="right", fill="y")
        self.scroll_canvas.pack(side="left", fill="both", expand=True)

        self.scroll_frame = ttk.Frame(self.scroll_canvas)
        self.scroll_window = self.scroll_canvas.create_window(
            (0, 0), window=self.scroll_frame, anchor="nw",
        )

        self.scroll_frame.bind("<Configure>", self._on_frame_configure)
        self.scroll_canvas.bind("<Configure>", self._on_canvas_configure)

        # Molette souris : vertical et horizontal
        self.scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel_y)
        self.scroll_canvas.bind_all("<Shift-MouseWheel>", self._on_mousewheel_x)
        self.scroll_canvas.bind_all("<Button-4>", self._on_mousewheel_y)
        self.scroll_canvas.bind_all("<Button-5>", self._on_mousewheel_y)
        self.scroll_canvas.bind_all("<Shift-Button-4>", self._on_mousewheel_x)
        self.scroll_canvas.bind_all("<Shift-Button-5>", self._on_mousewheel_x)

        # Console à droite
        self._create_console_panel(self.right_panel)
        # ========== Code pour afficher les prints dans l'app FIN
        main = ttk.Frame(self.scroll_frame, padding=15)
        main.pack(fill="both", expand=True)

        conn = ttk.LabelFrame(main, text="Connexion", padding=10)
        conn.pack(fill="x", pady=5)

        self.port = ttk.Entry(conn, width=10)
        self.port.insert(0, "COM4")
        self.port.pack(side="left", padx=5)

        ttk.Button(conn, text="Connecter", command=self.connect).pack(side="left")

        # ===== DÉBUT AJOUT — toggle simulation =====
        self.sim_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            conn, text="Simulation", variable=self.sim_var,
            command=self._toggle_sim,
        ).pack(side="right", padx=5)
        # ===== FIN AJOUT — toggle simulation =====

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
        self.pos_ref.insert(0, "300")
        self.pos_ref.pack(side="left", padx=5)

        ttk.Button(ref_frame, text="Envoyer", command=self.send_ref).pack(side="left")

        pid_frame = ttk.LabelFrame(main, text="Régulateurs", padding=10)
        pid_frame.pack(fill="x", pady=5)

        ttk.Label(pid_frame, text="Position (Kp Ki Kd)").grid(row=0, column=0)

        self.kp = ttk.Entry(pid_frame, width=10)
        self.ki = ttk.Entry(pid_frame, width=10)
        self.kd = ttk.Entry(pid_frame, width=10)

        self.kp.insert(0, "0.12")
        self.ki.insert(0, "12")
        self.kd.insert(0, "0.012")

        self.kp.grid(row=0, column=1)
        self.ki.grid(row=0, column=2)
        self.kd.grid(row=0, column=3)

        ttk.Button(pid_frame, text="Appliquer", command=self.send_pid_pos).grid(row=0, column=4)

        ttk.Label(pid_frame, text="Courant (Kp Ki)").grid(row=1, column=0)

        self.kp_c = ttk.Entry(pid_frame, width=10)
        self.ki_c = ttk.Entry(pid_frame, width=10)

        self.kp_c.insert(0, "0.4")
        self.ki_c.insert(0, "165")

        self.kp_c.grid(row=1, column=1)
        self.ki_c.grid(row=1, column=2)

        ttk.Button(pid_frame, text="Appliquer", command=self.send_pid_cur).grid(row=1, column=4)

        # ===== DÉBUT MODIFICATION — affichage Masse temps réel + Masse stable =====
        measure_frame = ttk.LabelFrame(main, text=f"Mesure (Affichage à chaque {masseRT_affichage} ms)", padding=10)
        measure_frame.pack(fill="x", pady=5)

        # LED de stabilité (à droite)
        self.canvas = tk.Canvas(measure_frame, width=30, height=30)
        self.canvas.pack(side="left", padx=10)
        self.led = self.canvas.create_oval(3, 3, 25, 25, fill="red")

        # Colonne gauche : Masse temps réel
        rt_frame = ttk.Frame(measure_frame)
        rt_frame.pack(side="left", padx=15)

        ttk.Label(rt_frame, text="Masse temps réel :").pack(anchor="w")
        self.masse_rt = tk.StringVar(value="--- g  /  --- kg")
        ttk.Label(
            rt_frame,
            textvariable=self.masse_rt,
            font=("Arial", 12),
            width=20,
            anchor="w"
        ).pack(anchor="w")

        # Colonne Milieu : Masse (stable, après moyennage)
        st_frame = ttk.Frame(measure_frame)
        st_frame.pack(side="left", padx=15)

        ttk.Label(st_frame, text="Masse moyennée :").pack(anchor="w")
        self.masse_stable = tk.StringVar(value="--- g  /  --- kg")
        ttk.Label(
            st_frame,
            textvariable=self.masse_stable,
            font=("Arial", 14, "bold"),
            width=20,
            anchor="w"
        ).pack(anchor="w")

        # Colonne droite : Masse lock après moyennage (stable, après moyennage)
        lt_frame = ttk.Frame(measure_frame)
        lt_frame.pack(side="left", padx=15)

        ttk.Label(lt_frame, text="Masse :").pack(anchor="w")
        self.masse_stable_lock = tk.StringVar(value="--- g  /  --- kg")
        ttk.Label(
            lt_frame,
            textvariable=self.masse_stable_lock,
            font=("Arial", 14, "bold"),
            width=20,
            anchor="w"
        ).pack(anchor="w")

        # Variables pour la conversion
        self.cal_dict = masse.load_calibration()
        self.cal_model = "affine"    # Modèle par défaut
        self.tare_masse = 0.0        # Tare en grammes (pour la masse affichée)

        # Lancer le polling d'affichage
        self.root.after(100, self._update_masse_display)
        # ===== FIN MODIFICATION — affichage Masse temps réel + Masse stable =====

        action = ttk.Frame(main)
        action.pack(pady=10)

        ttk.Button(action, text="Start", command=self.start).grid(row=0, column=0, padx=5)
        ttk.Button(action, text="Stop", command=self.stop).grid(row=0, column=1, padx=5)
        self.tare_btn = ttk.Button(action, text="Tare", command=self.tare, state="disabled")
        self.tare_btn.grid(row=0, column=2, padx=5)
        ttk.Button(action, text="Reset PID", command=self.reset_pid).grid(row=0, column=3, padx=5)
        ttk.Button(action, text="Identification complète", command=self.run_identification).grid(row=0, column=4, padx=5)
        
        # ===== DÉBUT AJOUT — section Calibration dans la fenêtre principale =====
        self._create_calibration_section(main)
        # ===== FIN AJOUT — section Calibration dans la fenêtre principale =====

    # ========== Code pour afficher les prints dans l'app DEBUT
    def _create_console_panel(self, parent):
        console_frame = ttk.LabelFrame(parent, text="Console", padding=8)
        console_frame.pack(fill="both", expand=True)

        top = ttk.Frame(console_frame)
        top.pack(fill="x", pady=(0, 5))

        self.console_autoscroll = tk.BooleanVar(value=True)

        ttk.Button(top, text="Clear", command=self._clear_console).pack(side="left")
        ttk.Checkbutton(
            top,
            text="Auto-scroll",
            variable=self.console_autoscroll
        ).pack(side="right")

        self.console = ScrolledText(
            console_frame,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
            height=25
        )
        self.console.pack(fill="both", expand=True)


    def _append_console(self, text, tag=None):
        if not hasattr(self, "console"):
            return

        self.console.configure(state="normal")
        self.console.insert("end", text, tag)
        if self.console_autoscroll.get():
            self.console.see("end")
        self.console.configure(state="disabled")

    def _clear_console(self):
        if not hasattr(self, "console"):
            return

        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
    # ========== Code pour afficher les prints dans l'app FIN

    # ===== DÉBUT AJOUT — méthodes de la section Calibration (UI principale) =====
    def _create_calibration_section(self, parent):
        """Crée la section Calibration dans la fenêtre principale."""
        cal_frame = ttk.LabelFrame(parent, text="Calibration", padding=10)
        cal_frame.pack(fill="x", pady=5)

        # Ligne 1 : Nombre de masses
        row1 = ttk.Frame(cal_frame)
        row1.pack(fill="x", pady=2)

        ttk.Label(row1, text="Nombre de masses (min 3) :").pack(side="left")
        self.cal_num_masses = tk.IntVar(value=3)
        self.cal_num_spin = tk.Spinbox(
            row1, from_=3, to=20, increment=1, width=5,
            textvariable=self.cal_num_masses,
        )
        self.cal_num_spin.pack(side="left", padx=5)
        # Molette de la souris pour incrémenter/décrémenter
        self.cal_num_spin.bind("<MouseWheel>", self._scroll_num_masses)

        # Ligne 2 : Temps de moyennage
        row2 = ttk.Frame(cal_frame)
        row2.pack(fill="x", pady=2)

        ttk.Label(row2, text="Temps de moyennage (ms, min 500) :").pack(side="left")
        self.cal_avg_time = tk.IntVar(value=500)
        self.cal_avg_spin = tk.Spinbox(
            row2, from_=500, to=30000, increment=500, width=7,
            textvariable=self.cal_avg_time,
        )
        self.cal_avg_spin.pack(side="left", padx=5)
        self.cal_avg_spin.bind("<MouseWheel>", self._scroll_avg_time)

        # Ligne 3 : Info ADC
        row3 = ttk.Frame(cal_frame)
        row3.pack(fill="x", pady=2)
        ttk.Label(row3, text=f"ADC : {masse.ADC_BITS} bits (0 – 5 V)").pack(side="left")

        # ===== DÉBUT AJOUT — sélection du modèle de calibration =====
        row_model = ttk.Frame(cal_frame)
        row_model.pack(fill="x", pady=2)
        ttk.Label(row_model, text="Modèle de calibration :").pack(side="left")
        self.cal_model_labels = {
            "Affine": "affine",
            "Quadratique": "quadratic",
            "Par morceaux": "piecewise",
        }

        self.cal_model_var = tk.StringVar(value="Affine")

        model_combo = ttk.Combobox(
            row_model,
            textvariable=self.cal_model_var,
            values=list(self.cal_model_labels.keys()),
            state="readonly",
            width=12,
        )
        model_combo.pack(side="left", padx=5)
        model_combo.bind("<<ComboboxSelected>>", self._on_model_changed)
        # ===== FIN AJOUT — sélection du modèle de calibration =====

        # Ligne boutons
        btn_row = ttk.Frame(cal_frame)
        btn_row.pack(pady=5)

        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        btn_row.columnconfigure(2, weight=1)

        ttk.Button(
            btn_row,
            text="Lancer la calibration",
            command=self._launch_calibration,
        ).grid(row=0, column=1, padx=5)

        ttk.Button(
            btn_row,
            text="Calcul résultat d'une calibration existante",
            command=self._cal_recalcul_resultat,
        ).grid(row=0, column=2, padx=5)

        self.btn_update_tps_moy = ttk.Button(
            btn_row,
            text="Update temps moyennage",
            command=self.update_tps_moy,
            state="disabled"
        )
        self.btn_update_tps_moy.grid(row=0, column=0, padx=5)

        # Zone des résultats (remplie après la calibration)
        self.cal_results_frame = ttk.LabelFrame(
            cal_frame, text="Résultats de calibration", padding=5,
        )
        self.cal_results_frame.pack(fill="both", expand=True, pady=5)

        # Frame gauche : tableau de résultats
        self.cal_table_frame = ttk.Frame(self.cal_results_frame)
        self.cal_table_frame.pack(side="left", fill="both", padx=5)

        # Frame droite : graphique
        self.cal_graph_frame = ttk.Frame(self.cal_results_frame)
        self.cal_graph_frame.pack(side="left", fill="both", expand=True, padx=5)

    def _scroll_num_masses(self, event):
        """Molette sur le champ nombre de masses."""
        current = self.cal_num_masses.get()
        if event.delta > 0:
            self.cal_num_masses.set(current + 1)
        elif event.delta < 0 and current > 3:
            self.cal_num_masses.set(current - 1)

    def _scroll_avg_time(self, event):
        """Molette sur le champ temps de moyennage."""
        current = self.cal_avg_time.get()
        if event.delta > 0:
            self.cal_avg_time.set(current + 500)
        elif event.delta < 0 and current > 1000:
            self.cal_avg_time.set(current - 500)

    # ===== DÉBUT AJOUT — changement de modèle de calibration =====
    def _on_model_changed(self, event=None):
        """Appelée quand l'utilisateur change le modèle de calibration."""
        selected_label = self.cal_model_var.get()
        self.cal_model = self.cal_model_labels[selected_label]
        # Recalculer la tare avec le nouveau modèle
        if self.cal_dict and len(self.cal_dict) >= 2 and self.offset != 0:
            self.tare_masse = masse.convert_masse(
                self.offset, self.cal_dict, self.cal_model
            )

    def update_tps_moy(self):
        self.min_stable_time = self.cal_avg_time.get() / 1000
        print(f"Nouveau temps de moyennage set à {self.min_stable_time} secondes")

    # ===== FIN AJOUT — changement de modèle de calibration =====

    def _launch_calibration(self):
        """Ouvre la fenêtre de calibration et démarre le processus."""
        print("Début calibration")
        if not self.ser and not self.sim_mode:
            messagebox.showerror("Erreur", "Pas connecté au port série.")
            return

        if self.cal_window is not None:
            self.cal_window.focus()
            return

        num = self.cal_num_masses.get()
        avg = self.cal_avg_time.get()

        if num < 3:
            messagebox.showwarning("Attention", "Minimum 3 masses de calibration.")
            return
        if avg < 1000:
            messagebox.showwarning("Attention", "Temps de moyennage minimum 1000 ms.")
            return

        # S'assurer qu'on est en mode asservi
        self.send(b'N')

        # Créer la calibration (masse.py)
        masse.init_calibration(
        n_masses=num,
        avg_time_ms=avg,
        get_courant_fn=lambda: self.last_courant,
        get_flag_fn=lambda: self.stable,
        )

        self._open_calibration_window()

    def _open_calibration_window(self):
        """Crée et affiche la fenêtre dédiée à la calibration."""
        self.cal_window = tk.Toplevel(self.root)
        self.cal_window.title("Calibration en cours")
        self.cal_window.geometry("400x300")
        self.cal_window.protocol("WM_DELETE_WINDOW", self._cal_stop)

        pad = ttk.Frame(self.cal_window, padding=15)
        pad.pack(fill="both", expand=True)

        # Info masse courante
        info = ttk.Frame(pad)
        info.pack(fill="x", pady=5)

        ttk.Label(info, text="Masse n° :").pack(side="left")
        self.cal_mass_label = ttk.Label(info, text="1", font=("Arial", 14, "bold"))
        self.cal_mass_label.pack(side="left", padx=5)

        total_label = f" / {masse.num_masses}"
        ttk.Label(info, text=total_label).pack(side="left")

        # Champ valeur réelle de la masse
        val_frame = ttk.Frame(pad)
        val_frame.pack(fill="x", pady=5)

        ttk.Label(val_frame, text="Masse réelle (g) :").pack(side="left")
        self.cal_masse_entry = ttk.Entry(val_frame, width=10)
        self.cal_masse_entry.pack(side="left", padx=5)
        self.cal_masse_entry.focus()

        # Statut
        self.cal_status = tk.StringVar(value="En attente de la masse sur le plateau...")
        ttk.Label(pad, textvariable=self.cal_status, wraplength=350).pack(pady=5)

        # Case à cocher : Nouvelle masse déposée
        self.cal_checkbox_var = tk.BooleanVar(value=False)
        self.cal_checkbox = ttk.Checkbutton(
            pad,
            text="Nouvelle masse déposée sur le plateau",
            variable=self.cal_checkbox_var,
            command=self._cal_checkbox_changed,
        )
        self.cal_checkbox.pack(pady=5)

        # Boutons
        btn_frame = ttk.Frame(pad)
        btn_frame.pack(pady=10)

        self.cal_prev_btn = ttk.Button(
            btn_frame, text="Previous", command=self._cal_previous,
        )
        self.cal_prev_btn.grid(row=0, column=0, padx=5)

        self.cal_next_btn = ttk.Button(
            btn_frame, text="Next", command=self._cal_next, state="disabled",
        )
        self.cal_next_btn.grid(row=0, column=1, padx=5)

        self.cal_stop_btn = ttk.Button(
            btn_frame, text="Stop", command=self._cal_stop,
        )
        self.cal_stop_btn.grid(row=0, column=2, padx=5)

        # Mettre à jour le texte du bouton si dernière masse
        self._cal_update_display()

    def _cal_update_display(self):
        """Met à jour l'affichage de la fenêtre de calibration."""
        if self.cal_window is None:
            return

        idx = masse.current_index
        self.cal_mass_label.config(text=str(idx + 1))

        # Pré-remplir la valeur de masse si déjà saisie
        self.cal_masse_entry.delete(0, tk.END)
        if idx < len(masse.results) and masse.results[idx] is not None:
            self.cal_masse_entry.insert(0, str(masse.results[idx]["masse_g"]))

        # Bouton Next ou End
        if masse.is_last_mass():
            self.cal_next_btn.config(text="End")
        else:
            self.cal_next_btn.config(text="Next")

        # Désactiver Next tant que nextMasse n'est pas True
        self.cal_next_btn.config(state="disabled")

        # Réinitialiser la checkbox
        self.cal_checkbox_var.set(False)
        self.cal_checkbox.config(state="normal")

        self.cal_status.set("En attente de la masse sur le plateau...")

    def _cal_checkbox_changed(self):
        """Appelée quand la case 'Nouvelle masse déposée' change d'état."""
        if self.cal_checkbox_var.get():
            # Case cochée → signaler à masse.py de commencer la collecte
            self.cal_checkbox.config(state="disabled")
            self.cal_status.set("Stabilisation et moyennage en cours...")
            masse.start_next_masse(calibration_mode=True)
            # Lancer un polling pour activer le bouton Next quand prêt
            self._cal_poll_next_ready()

    def _cal_poll_next_ready(self):
        """Vérifie périodiquement si nextMasse est True."""
        if self.cal_window is None:
            return

        if masse.nextMasse:
            self.cal_next_btn.config(state="normal")
            cur = masse.get_cur_moyen()
            self.cal_status.set(
                f"Moyenne : {cur:.1f} ADC "
                f"({masse.adc_to_voltage(cur):.4f} V)  —  "
                "Appuyez sur Next quand prêt."
            )
            # Continuer à mettre à jour l'affichage de la moyenne
            self._cal_poll_update_mean()
        else:
            self.cal_window.after(100, self._cal_poll_next_ready)

    def _cal_poll_update_mean(self):
        """Met à jour l'affichage de la moyenne tant que la collecte continue."""
        if self.cal_window is None:
            return
        if not masse.nextMasse:
            return

        cur = masse.get_cur_moyen()
        self.cal_status.set(
            f"Moyenne : {cur:.1f} ADC "
            f"({masse.adc_to_voltage(cur):.4f} V)  —  "
            "Appuyez sur Next quand prêt."
        )
        self.cal_window.after(200, self._cal_poll_update_mean)

    def _cal_next(self):
        """Bouton Next / End pressé."""
        print("Next masse de calibration")
        if not masse.nextMasse:
            return

        # Lire la masse réelle saisie
        try:
            masse_g = float(self.cal_masse_entry.get())
        except ValueError:
            messagebox.showwarning(
                "Entrée invalide",
                "Entrez une valeur numérique pour la masse (g).",
                parent=self.cal_window,
            )
            return

        # Valider la masse courante
        masse.validate_current(masse_g)

        # Vérifier si la calibration est terminée
        if masse.is_done():
            self._cal_finish()
        else:
            self._cal_update_display()

    def _cal_previous(self):
        """Bouton Previous pressé."""
        print("Masse de calibration précédente")
        masse.go_previous()
        self._cal_update_display()

    def _cal_stop(self):
        """Bouton Stop pressé ou fermeture de la fenêtre."""
        print("Arrêt de la calibration")
        masse.stop_collecting()

        if self.cal_window is not None:
            self.cal_window.destroy()
            self.cal_window = None

    def _cal_finish(self):
        """Calibration terminée. Sauvegarde, ferme la fenêtre, affiche les résultats."""
        cal_path = masse.save_calibration()
        print(f"Calibration sauvegardée : {cal_path}")

        # ===== DÉBUT AJOUT — recharger le dictionnaire de calibration =====
        self.cal_dict = masse.load_calibration()
        self.tare_masse = 0.0  # Reset tare après nouvelle calibration
        # ===== FIN AJOUT — recharger le dictionnaire de calibration =====

        if self.cal_window is not None:
            self.cal_window.destroy()
            self.cal_window = None

        self._display_calibration_results()

    def _cal_recalcul_resultat(self):
        """Bouton pour recalculer les résultats d'une calibration déjà existante"""
        print("Recalcul des résultats")
        self.cal_dict = masse.load_calibration()

        if not self.cal_dict or len(self.cal_dict) < 2:
            messagebox.showwarning("Attention", "Aucun fichier calibration.json trouvé ou moins de 2 points.")
            return

        # Reconstruire masse.results à partir du dictionnaire chargé
        masse.results = []
        for i, (masse_str, tension_v) in enumerate(self.cal_dict.items()):
            masse.results.append({
                "numero": i + 1,
                "masse_g": float(masse_str),
                "adc_moyen": tension_v / masse.V_REF * masse.ADC_MAX,
                "tension_v": float(tension_v),
            })

        print(f"Calibration importée : {len(masse.results)} points")
        self._display_calibration_results()

    def _display_calibration_results(self):
        """
        Affiche les résultats dans la section Calibration de la fenêtre principale :
        tableau (numéro, masse, tension) + graphique calibration + graphique résidus.
        """
        results = masse.get_valid_results()
        if not results:
            return

        # Vider l'ancien contenu
        for w in self.cal_table_frame.winfo_children():
            w.destroy()
        for w in self.cal_graph_frame.winfo_children():
            w.destroy()

        # En-têtes du tableau
        headers = ["#", "Masse (g)", "Tension (V)"]
        for col, h in enumerate(headers):
            lbl = ttk.Label(self.cal_table_frame, text=h, font=("Arial", 9, "bold"))
            lbl.grid(row=0, column=col, padx=4, pady=2)

        # Lignes du tableau
        for i, r in enumerate(results):
            ttk.Label(self.cal_table_frame, text=str(r["numero"])).grid(
                row=i + 1, column=0, padx=4, pady=1,
            )
            ttk.Label(self.cal_table_frame, text=f"{r['masse_g']:.2f}").grid(
                row=i + 1, column=1, padx=4, pady=1,
            )
            ttk.Label(self.cal_table_frame, text=f"{r['tension_v']:.4f}").grid(
                row=i + 1, column=2, padx=4, pady=1,
            )

        tensions = [r["tension_v"] for r in results]
        masses_g = [r["masse_g"] for r in results]

        # --- Graphique 1 : Courbe de calibration ---
        fig = Figure(figsize=(3.5, 2.5), dpi=100)
        ax = fig.add_subplot(111)
        ax.plot(tensions, masses_g, "o-", markersize=6)
        ax.set_xlabel("Tension (V)")
        ax.set_ylabel("Masse (g)")
        ax.set_title("Courbe de calibration")
        ax.grid(True)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self.cal_graph_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        # ===== DÉBUT AJOUT — graphique des résidus =====

        # Frame pour le graphique des résidus + checkboxes
        residual_frame = ttk.LabelFrame(
            self.cal_graph_frame, text="Analyse des résidus", padding=5,
        )
        residual_frame.pack(fill="both", expand=True, pady=5)

        # Checkboxes pour afficher/cacher chaque modèle
        cb_frame = ttk.Frame(residual_frame)
        cb_frame.pack(fill="x")

        self._res_show_affine = tk.BooleanVar(value=True)
        self._res_show_quadratic = tk.BooleanVar(value=True)
        self._res_show_piecewise = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            cb_frame, text="Affine", variable=self._res_show_affine,
            command=self._redraw_residuals,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(
            cb_frame, text="Quadratique", variable=self._res_show_quadratic,
            command=self._redraw_residuals,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(
            cb_frame, text="Par morceaux", variable=self._res_show_piecewise,
            command=self._redraw_residuals,
        ).pack(side="left", padx=5)

        # Frame pour le canvas du graphique résidus
        self._res_canvas_frame = ttk.Frame(residual_frame)
        self._res_canvas_frame.pack(fill="both", expand=True)

        # Stocker les données pour le redraw
        self._res_tensions = tensions
        self._res_masses = masses_g

        self._redraw_residuals()

        # ===== FIN AJOUT — graphique des résidus =====

    # ===== DÉBUT AJOUT — dessin du graphique des résidus =====

    def _redraw_residuals(self):
        """Redessine le graphique des résidus selon les checkboxes cochées."""
        # Vider le canvas précédent
        for w in self._res_canvas_frame.winfo_children():
            w.destroy()

        tensions = self._res_tensions
        masses_g = self._res_masses
        cal_dict = self.cal_dict

        if not cal_dict or len(cal_dict) < 2:
            return

        fig = Figure(figsize=(3.5, 2.5), dpi=100)
        ax = fig.add_subplot(111)

        models = [
            ("affine",    self._res_show_affine,    "o-",  "Affine"),
            ("quadratic", self._res_show_quadratic, "s--", "Quadratique"),
            ("piecewise", self._res_show_piecewise, "^:",  "Par morceaux"),
        ]

        for model_name, var, style, label in models:
            if not var.get():
                continue

            residuals = []
            for v, m in zip(tensions, masses_g):
                # Reconvertir la tension en ADC pour passer par convert_masse
                adc_val = v / masse.V_REF * masse.ADC_MAX
                m_hat = masse.convert_masse(adc_val, cal_dict, model_name)
                residuals.append(m - m_hat)

            ax.plot(tensions, residuals, style, label=label, markersize=5)

        # Ligne de référence à 0
        ax.axhline(y=0, color="gray", linewidth=0.8, linestyle="-")

        ax.set_xlabel("Tension (V)")
        ax.set_ylabel("Résidu (g)")
        ax.set_title("Résidus : m_réel − m_estimé")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self._res_canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    # ===== FIN AJOUT — dessin du graphique des résidus =====

    # ===== FIN AJOUT — méthodes de la section Calibration =====

    # ===== DÉBUT AJOUT — mise à jour continue de l'affichage masse =====

    def _format_masse(self, masse_g):
        """Formate une masse en g et kg avec précision 0.1 g."""
        masse_kg = masse_g / 1000.0
        return f"{masse_g:.1f} g  /  {masse_kg:.4f} kg"

    def _update_masse_display(self):
        """
        Polling continu (~100ms) pour mettre à jour les deux affichages :
        - Masse temps réel : valeur instantanée (même si balance instable)
        - Masse : valeur après stabilisation et moyennage
        Les deux sont affichées en grammes et kilogrammes.
        Si une calibration est disponible, les valeurs ADC sont converties
        en masse via le modèle de calibration. Sinon, affichage brut ADC.
        """
        # --- Masse temps réel ---
        cur = self.last_courant
        if self.cal_dict and len(self.cal_dict) >= 2:
            masse_rt_g = masse.convert_masse(cur, self.cal_dict, self.cal_model)
            masse_rt_g -= self.tare_masse
            self.masse_rt.set(self._format_masse(masse_rt_g))
        else:
            raw = cur - self.offset
            self.masse_rt.set(f"{raw} ADC")

        # --- Masse (stable, après moyennage) ---
        if self.avg_value is not None:
            if self.cal_dict and len(self.cal_dict) >= 2:
                masse_st_g = masse.convert_masse(
                    self.avg_value, self.cal_dict, self.cal_model
                )
                masse_st_g -= self.tare_masse
                self.masse_stable.set(self._format_masse(masse_st_g))
            else:
                raw = int(self.avg_value - self.offset)
                self.masse_stable.set(f"{raw} ADC")
        else:
            self.masse_stable.set("--- g  /  --- kg")

        # --- Masse lock (stable, après moyennage) ---
        if self.avg_value_lock is not None:
            if self.cal_dict and len(self.cal_dict) >= 2:
                masse_lt_g = masse.convert_masse(
                    self.avg_value_lock, self.cal_dict, self.cal_model
                )
                masse_lt_g -= self.tare_masse
                self.masse_stable_lock.set(self._format_masse(masse_lt_g))
            else:
                raw = int(self.avg_value_lock - self.offset)
                self.masse_stable_lock.set(f"{raw} ADC")
            self.avg_value_lock = None  # Affiché une fois, réinitialisé pour la prochaine mesure
        #else:
            #self.masse_stable_lock.set("--- g  /  --- kg")

        self.root.after(masseRT_affichage, self._update_masse_display)

    # ===== FIN AJOUT — mise à jour continue de l'affichage masse =====

    # ===== DÉBUT AJOUT — méthodes de défilement (scroll) =====

    def _on_frame_configure(self, event):
        """Met à jour la zone de défilement quand le contenu change de taille."""
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))
        self._update_scrollbar_visibility()

    def _on_canvas_configure(self, event):
        """Ajuste le contenu quand la fenêtre est redimensionnée."""
        canvas_w = event.width
        canvas_h = event.height
        frame_w = self.scroll_frame.winfo_reqwidth()
        frame_h = self.scroll_frame.winfo_reqheight()

        # Si la fenêtre est plus large que le contenu, étirer le contenu
        new_w = max(canvas_w, frame_w)
        self.scroll_canvas.itemconfig(self.scroll_window, width=new_w)

        self._update_scrollbar_visibility()

    def _update_scrollbar_visibility(self):
        """Affiche ou cache les scrollbars selon si le contenu dépasse la fenêtre."""
        self.scroll_canvas.update_idletasks()
        bbox = self.scroll_canvas.bbox("all")
        if not bbox:
            return

        content_w = bbox[2] - bbox[0]
        content_h = bbox[3] - bbox[1]
        canvas_w = self.scroll_canvas.winfo_width()
        canvas_h = self.scroll_canvas.winfo_height()

        # Vertical
        if content_h <= canvas_h:
            self.v_scrollbar.pack_forget()
        else:
            self.v_scrollbar.pack(side="right", fill="y")

        # Horizontal
        if content_w <= canvas_w:
            self.h_scrollbar.pack_forget()
        else:
            self.h_scrollbar.pack(side="bottom", fill="x")

    def _on_mousewheel_y(self, event):
        """Défilement vertical avec la molette de la souris."""
        # Vérifier si le scroll est nécessaire
        bbox = self.scroll_canvas.bbox("all")
        if not bbox:
            return
        if bbox[3] - bbox[1] <= self.scroll_canvas.winfo_height():
            return

        # Windows / macOS
        if event.num == 0:
            self.scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        # Linux
        elif event.num == 4:
            self.scroll_canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            self.scroll_canvas.yview_scroll(3, "units")

    def _on_mousewheel_x(self, event):
        """Défilement horizontal avec Shift + molette."""
        bbox = self.scroll_canvas.bbox("all")
        if not bbox:
            return
        if bbox[2] - bbox[0] <= self.scroll_canvas.winfo_width():
            return

        if event.num == 0:
            self.scroll_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        elif event.num == 4:
            self.scroll_canvas.xview_scroll(-3, "units")
        elif event.num == 5:
            self.scroll_canvas.xview_scroll(3, "units")

    # ===== FIN AJOUT — méthodes de défilement (scroll) =====

    # ================= SERIAL =================
    def connect(self):
        print(f"Connection série au port {self.port.get()}")

        self.send_ref()
        self.send_pid_pos()
        self.send_pid_cur()

        # ===== DÉBUT AJOUT — connexion en mode simulation =====
        if self.sim_var.get():
            self.sim_mode = True
            self.ser = None
            self.sim_running = True
            self.sim_thread = threading.Thread(target=self._sim_reader, daemon=True)
            self.sim_thread.start()
            print("Simulation activée")
            # ===== DÉBUT AJOUT — init mesure pour usage hors calibration =====
            masse.init_measurement(
            avg_time_ms=self.cal_avg_time.get(),
            get_courant_fn=lambda: self.last_courant,
            get_flag_fn=lambda: self.stable,
            )
            # ===== FIN AJOUT =====
            return
        # ===== FIN AJOUT — connexion en mode simulation =====

        self.sim_mode = False
        self.ser = serial.Serial(self.port.get(), BAUDRATE, timeout=0)
        time.sleep(2)
        threading.Thread(target=self.reader, daemon=True).start()
        # ===== DÉBUT AJOUT — init mesure pour usage hors calibration =====
        masse.init_measurement(
        avg_time_ms=self.cal_avg_time.get(),
        get_courant_fn=lambda: self.last_courant,
        get_flag_fn=lambda: self.stable,
        )
        # ===== FIN AJOUT =====

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

            # ===== LISSAGE PRÉALABLE (EMA) =====
            # alpha entre 0.1 (très lent) et 0.5 (réactif). Ajuste selon tes tests.
            alpha = 0.2 
            if not hasattr(self, 'lissage_cur'): self.lissage_cur = cur
            self.lissage_cur = (alpha * cur) + (1 - alpha) * self.lissage_cur

            # ===== GESTION STABILITÉ SUR VALEUR LISSÉE =====
            now = time.time()
            self.stab_buffer.append(self.lissage_cur) # On travaille sur la valeur filtrée

            if len(self.stab_buffer) < self.stab_buffer.maxlen:
                self.stable = False
                self.stable_since = None
                self.canvas.itemconfig(self.led, fill="orange")
            else:
                values = list(self.stab_buffer)
                avg = sum(values) / len(values)
                
                span = max(values) - min(values)
                std_dev = statistics.stdev(values) if len(values) > 1 else 0

                # On peut aussi augmenter un peu les seuils pour tolérer un léger bruit résiduel
                stable_now = (span <= self.span_threshold) and (std_dev <= self.std_threshold)

                if stable_now:
                    if self.stable_since is None:
                        self.stable_since = now

                    if (now - self.stable_since) >= self.min_stable_time:
                        if not self.stable:
                            self.stable = True
                            self.tare_btn.config(state="normal") # Activer le bouton Tare
                            self.btn_update_tps_moy.config(state="normal") # Activer le tps moy
                            self.avg_value = avg
                            print(f"Stabilisé à {self.avg_value:.1f} ADC (span={span:.1f}, std={std_dev:.2f})")
                            if self.masse_lock_flag:
                                self.avg_value_lock = avg
                                self.masse_lock_flag = False
                                print(f"Masse lock définie à {self.avg_value_lock:.1f} ADC")
                            if self.init_tare_flag:
                                self.tare()
                                self.init_tare_flag = False
                                print(f"Offset initial défini à {self.offset:.1f} ADC")
                            self.canvas.itemconfig(self.led, fill="green")
                    else:
                        self.stable = False
                        self.canvas.itemconfig(self.led, fill="orange")
                else:
                    # On ne repasse en ROUGE que si l'instabilité dure un tout petit peu
                    # ou si le dépassement est flagrant (ex: 2x le seuil)
                    if span > (self.span_threshold * 1.5):
                        self.stable = False
                        self.tare_btn.config(state="disabled") # Désactiver le bouton Tare
                        self.btn_update_tps_moy.config(state="normal") # Désctiver le tps moy
                        self.stable_since = None
                        self.masse_lock_flag = True
                        self.canvas.itemconfig(self.led, fill="red")
                        self.masse_stable_lock.set("--- g  /  --- kg")

            self.data.append((time.time(), pos, cur, cmd_pos, cmd_cur))

    # ===== DÉBUT AJOUT — simulation Arduino =====

    def _toggle_sim(self):
        """Active/désactive le mode simulation (avant de connecter)."""
        if self.sim_var.get():
            self.port.config(state="disabled")
        else:
            self.port.config(state="normal")

    def _sim_reader(self):
        """
        Thread de simulation. Génère des données fictives au même rythme
        que l'Arduino (une trame 'T' toutes les ~20 ms ≈ 50 Hz).

        Comportement simulé :
        - Position oscille autour de 300 (positionRef) avec du bruit.
        - Quand on change le PWM, le courant réagit proportionnellement.
        - flag (mesureValide) passe à True après quelques cycles de stabilisation.
        """
        t0 = time.monotonic()

        while self.sim_running:
            dt = time.monotonic() - t0

            # -- Position simulée : oscille autour de 300 + bruit --
            noise_pos = random.gauss(0, 2)
            # Le PWM déplace un peu la position (simule une force)
            pwm_effect = (self.sim_pwm - 50) * 0.3
            self.sim_position += (300.0 + pwm_effect - self.sim_position) * 0.1
            pos = int(max(0, min(1023, self.sim_position + noise_pos)))

            # -- Courant simulé : proportionnel au PWM + bruit --
            target_courant = 512 + (self.sim_pwm - 50) * 3.0
            self.sim_courant += (target_courant - self.sim_courant) * 0.15
            noise_cur = random.gauss(0, 1.5)
            cur = int(max(0, min(1023, self.sim_courant + noise_cur)))

            # -- Commandes simulées --
            cmd_pos = int(max(0, min(1023, 512 + (self.sim_pwm - 50) * 2)))
            cmd_cur = int(max(0, min(1023, self.sim_courant)))

            # -- Flag : stable après quelques cycles --
            self.sim_flag_counter += 1
            if self.sim_flag_counter > 25:  # ~0.5 sec de stabilisation
                flag = 1
            else:
                flag = 0

            # Injecter les données comme si ça venait du parse()
            self.last_courant = cur
            self.last_flag = flag

            self.root.after(0, self._sim_update_ui, pos, cur, cmd_pos, cmd_cur, flag)

            self.data.append((time.time(), pos, cur, cmd_pos, cmd_cur))

            time.sleep(0.020)  # 50 Hz, comme le main.cpp (toggleCounter % 10)

    def _sim_update_ui(self, pos, cur, cmd_pos, cmd_cur, flag):
        """Met à jour l'interface depuis le thread principal (thread-safe)."""
        # ===== DÉBUT MODIFICATION — affichage géré par _update_masse_display =====
        if flag:
            self.canvas.itemconfig(self.led, fill="green")
        else:
            self.canvas.itemconfig(self.led, fill="red")
        # ===== FIN MODIFICATION =====

    # ===== FIN AJOUT — simulation Arduino =====

    # ================= COMMANDES =================
    def send(self, b):
        # ===== DÉBUT AJOUT — envoi en mode simulation =====
        if self.sim_mode:
            self._sim_handle_command(b)
            return
        # ===== FIN AJOUT — envoi en mode simulation =====
        if self.ser:
            self.ser.write(b)
            
    def reset_pid(self):
        print("Reset PID")
        self.send(b'Z')

    # ===== DÉBUT AJOUT — interprétation commandes en simulation =====
    def _sim_handle_command(self, data):
        """Interprète les commandes envoyées à l'Arduino en mode simulation."""
        if not data:
            return
        cmd = data[0:1]
        if cmd == b'P' and len(data) >= 2:
            self.sim_pwm = data[1]
            self.sim_flag_counter = 0  # Reset stabilisation
        elif cmd == b'R' and len(data) >= 3:
            ref = struct.unpack('<H', data[1:3])[0]
            self.sim_position = float(ref)
            self.sim_flag_counter = 0
        elif cmd == b'N':
            self.sim_pwm = 50
            self.sim_flag_counter = 0
        elif cmd == b'I':
            self.sim_flag_counter = 0
        elif cmd == b'Z':
            # reset PID simulé = retour état stable
            self.sim_pwm = 50
            self.sim_flag_counter = 0
        # S, E, G, H : on ignore silencieusement en simulation
    # ===== FIN AJOUT — interprétation commandes en simulation =====

    def send_ref(self):
        self.send(b'R' + struct.pack('<H', int(self.pos_ref.get())))
        print(f"Position de référence set à {self.pos_ref.get()}")

    def send_pid_pos(self):
        self.send(b'G' + struct.pack('<fff',
                                     float(self.kp.get()),
                                     float(self.ki.get()),
                                     float(self.kd.get())))
        print(f"Régulateur de position appliqué P = {self.kp.get()} | I = {self.ki.get()} | D = {self.kd.get()}")

    def send_pid_cur(self):
        self.send(b'H' + struct.pack('<ff',
                                     float(self.kp_c.get()),
                                     float(self.ki_c.get())))
        print(f"Régulateur de courant appliqué P = {self.kp_c.get()} | I = {self.ki_c.get()}")

    # ===== DÉBUT MODIFICATION — tare basée sur la masse =====
    def tare(self):
        #self.offset = self.avg_value
        self.offset = self.last_courant
        print(f"Tare avec {self.offset:.1f}")
        self.masse_stable_lock.set("0.0 g  /  0.0 kg")
        # Si calibration disponible, stocker la masse actuelle comme tare
        if self.cal_dict and len(self.cal_dict) >= 2:
            self.tare_masse = masse.convert_masse(
                self.last_courant, self.cal_dict, self.cal_model
            )
            print(f"Tare avec {self.tare_masse}")
        else:
            self.tare_masse = 0.0
    # ===== FIN MODIFICATION — tare basée sur la masse =====

    # ================= START / STOP =================
    def start(self):
        print("Start oscilloscope")
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
        print("Stop oscilloscope")
        self.running = False
        self.plot_running = False
        self.send(b'E')
        self.send(b'P' + bytes([50]))

    # ================= IDENTIFICATION =================
    def run_identification(self):
        print("Run identification")
        if not self.ser and not self.sim_mode:
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
        # ========== Code pour afficher les prints dans l'app DEBUT
        try:
            sys.stdout = self._stdout
        except Exception:
            pass
        # ========== Code pour afficher les prints dans l'app FIN

        # ===== DÉBUT AJOUT — nettoyage calibration à la fermeture =====
        masse.stop_collecting()
        if self.cal_window is not None:
            try:
                self.cal_window.destroy()
            except Exception:
                pass
        # ===== FIN AJOUT — nettoyage calibration à la fermeture =====

        # ===== DÉBUT AJOUT — arrêt simulation =====
        self.sim_running = False
        # ===== FIN AJOUT — arrêt simulation =====

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