# ===== DÉBUT AJOUT CALIBRATION — constantes =====
CALIB_TARE_DURATION_S = 5.0        # Durée du tare de calibration (secondes)
CALIB_MEASURE_DURATION_S = 3.0     # Durée d'acquisition par masse (secondes)
CALIB_DATA_DIR = BASE_DIR / "dataCalibration"
# ===== FIN AJOUT CALIBRATION — constantes =====
 
 
# ===== DÉBUT AJOUT CALIBRATION — fonctions =====
 
@dataclass
class CalibrationResult:
    """Résultat de calibration pour une masse."""
    num: int                # Numéro de la masse (1-based)
    masse_reelle: float     # Masse réelle en grammes
    courant_raw: float      # Valeur numérique brute moyenne du courant
    courant_ref: float      # Valeur de référence du courant (tare)
    delta_raw: float        # courant_raw - courant_ref
    courant_amperes: float  # Valeur convertie en ampères
 
 
def collect_calib_samples(
    ser: serial.Serial,
    duration_s: float,
) -> List[int]:
    """Collecte les valeurs brutes de courant pendant une durée donnée.
 
    Utilise le protocole d'acquisition existant (paquets de 4 octets :
    2 octets position + 2 octets courant).
 
    Retourne la liste des valeurs de courant brutes collectées.
    """
    rx_buffer = bytearray()
    courant_values: List[int] = []
    deadline = time.monotonic() + duration_s
 
    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting > 0:
            rx_buffer.extend(ser.read(waiting))
 
        # Parser les paquets de 4 octets (position u16 + courant u16)
        while len(rx_buffer) >= 4:
            _position, courant = struct.unpack_from('<HH', rx_buffer, 0)
            del rx_buffer[:4]
            courant_values.append(courant)
 
        if ser.in_waiting == 0:
            time.sleep(SERIAL_POLL_SLEEP_S)
 
    # Vidange finale
    flush_deadline = time.monotonic() + 0.02
    while time.monotonic() < flush_deadline:
        waiting = ser.in_waiting
        if waiting > 0:
            rx_buffer.extend(ser.read(waiting))
        while len(rx_buffer) >= 4:
            _position, courant = struct.unpack_from('<HH', rx_buffer, 0)
            del rx_buffer[:4]
            courant_values.append(courant)
        if ser.in_waiting == 0:
            time.sleep(SERIAL_POLL_SLEEP_S)
 
    return courant_values
 
 
def convert_raw_to_amperes(delta_raw: float, adc_bits: int) -> float:
    """Convertit une valeur brute relative (après soustraction du courantRef)
    en ampères.
 
    La plage de lecture du capteur de courant est de -1.5 A à +1.5 A,
    mappée sur 0 à (2^adc_bits - 1).
    """
    adc_max = (2 ** adc_bits) - 1
    plage_courant = 3.0  # -1.5 A à +1.5 A
    return delta_raw * plage_courant / adc_max
 
 
def write_calib_csv(csv_path: Path, results: List[CalibrationResult]) -> None:
    """Enregistre les résultats de calibration dans un fichier CSV."""
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "num",
            "masse_reelle_g",
            "courant_raw",
            "courant_ref",
            "delta_raw",
            "courant_amperes",
        ])
        for r in results:
            writer.writerow([
                r.num,
                f"{r.masse_reelle:.4f}",
                f"{r.courant_raw:.6f}",
                f"{r.courant_ref:.6f}",
                f"{r.delta_raw:.6f}",
                f"{r.courant_amperes:.6f}",
            ])
 
 
def run_calibration(ser: serial.Serial) -> List[CalibrationResult]:
    """Exécute la procédure de calibration en ligne de commande.
 
    Étapes :
    1) Tare de calibration (5 s sans masse) → courantRef
    2) Pour chaque masse de calibration :
       - L'utilisateur place la masse et entre sa valeur réelle
       - Acquisition pendant CALIB_MEASURE_DURATION_S secondes
       - Possibilité de refaire (Previous) ou passer (Next)
    3) Conversion des valeurs brutes en ampères
    4) Sauvegarde CSV
 
    Retourne la liste des CalibrationResult (valeurs brutes conservées
    pour linéarisation future).
    """
    CALIB_DATA_DIR.mkdir(parents=True, exist_ok=True)
 
    # Paramètres utilisateur
    num_masses = ask_int_in_range(
        "Combien de masses de calibration ? : ", 1, 50
    )
    adc_bits = ask_int_in_range(
        "Nombre de bits de l'ADC ? : ", 8, 16
    )
 
    # S'assurer que le système est en mode normal (asservi)
    ser.write(b'N')
    ser.flush()
    time.sleep(0.05)
 
    # Vérifier que la balance est au repos
    is_ready = ask_yes_no(
        "La balance est-elle au repos, SANS aucune masse ? (O/N) : "
    )
    if not is_ready:
        print("Place la balance au repos sans masse, puis relance la calibration.")
        return []
 
    # --- Tare de calibration ---
    print(f"\nTare de calibration en cours ({CALIB_TARE_DURATION_S} secondes)...")
    print("Ne pas toucher à la balance.")
 
    send_start(ser)
    tare_values = collect_calib_samples(ser, CALIB_TARE_DURATION_S)
    send_stop(ser)
 
    if not tare_values:
        print("Erreur : aucune donnée reçue pendant le tare.")
        return []
 
    courant_ref = sum(tare_values) / len(tare_values)
    print(f"courantRef = {courant_ref:.6f} ({len(tare_values)} échantillons)")
 
    # --- Mesure de chaque masse ---
    masses_reelles: List[float] = [0.0] * num_masses
    courants_raw: List[float] = [0.0] * num_masses
 
    index = 0
    while index < num_masses:
        print(f"\n--- Masse {index + 1} / {num_masses} ---")
        print("Place la masse de calibration sur la balance.")
 
        # Saisir la valeur réelle
        while True:
            raw_input_val = input(f"Valeur réelle de la masse {index + 1} (en grammes) : ").strip()
            try:
                masse_val = float(raw_input_val)
                break
            except ValueError:
                print("Entrée invalide. Entre un nombre.")
 
        masses_reelles[index] = masse_val
 
        # Attendre que l'utilisateur soit prêt
        input("Appuie sur Entrée quand la balance est stable pour lancer l'acquisition...")
 
        # Acquisition
        print(f"Acquisition en cours ({CALIB_MEASURE_DURATION_S} secondes)...")
        send_start(ser)
        values = collect_calib_samples(ser, CALIB_MEASURE_DURATION_S)
        send_stop(ser)
 
        if not values:
            print("Attention : aucune donnée reçue. Réessaie.")
            continue
 
        courant_moyen = sum(values) / len(values)
        courants_raw[index] = courant_moyen
        delta = courant_moyen - courant_ref
        courant_A = convert_raw_to_amperes(delta, adc_bits)
 
        print(f"  Courant brut moyen : {courant_moyen:.2f}")
        print(f"  Delta (brut - ref) : {delta:.2f}")
        print(f"  Courant (A)        : {courant_A:.6f}")
        print(f"  ({len(values)} échantillons)")
 
        # Navigation
        if index < num_masses - 1:
            choix_prompt = "(N)ext / (P)revious / (S)top : "
        else:
            choix_prompt = "(E)nd / (P)revious / (S)top : "
 
        while True:
            choix = input(choix_prompt).strip().lower()
            if choix in {"n", "next", "e", "end"}:
                index += 1
                break
            elif choix in {"p", "previous", "prev"}:
                if index > 0:
                    index -= 1
                    print(f"Retour à la masse {index + 1}. La mesure sera refaite.")
                else:
                    print("Déjà à la première masse.")
                break
            elif choix in {"s", "stop"}:
                print("Calibration annulée.")
                return []
            else:
                print("Choix invalide.")
 
    # --- Calcul final et conversion ---
    print("\n=== Résultats de calibration ===")
    results: List[CalibrationResult] = []
 
    for i in range(num_masses):
        delta_raw = courants_raw[i] - courant_ref
        courant_A = convert_raw_to_amperes(delta_raw, adc_bits)
 
        result = CalibrationResult(
            num=i + 1,
            masse_reelle=masses_reelles[i],
            courant_raw=courants_raw[i],
            courant_ref=courant_ref,
            delta_raw=delta_raw,
            courant_amperes=courant_A,
        )
        results.append(result)
 
        print(f"  Masse {i + 1}: {masses_reelles[i]:.2f} g → "
              f"brut={courants_raw[i]:.2f}, "
              f"delta={delta_raw:.2f}, "
              f"courant={courant_A:.6f} A")
 
    # --- Sauvegarde CSV ---
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    csv_path = CALIB_DATA_DIR / f"calibration_{timestamp}.csv"
    write_calib_csv(csv_path, results)
    print(f"\nRésultats enregistrés : {csv_path}")
 
    return results
 
# ===== FIN AJOUT CALIBRATION — fonctions =====

        while True:
            # ===== DÉBUT AJOUT CALIBRATION — menu principal =====
            print("\nQue veux-tu faire ?")
            print("  0 = Test d'identification")
            print("  1 = Calibration")
            print("  Q = Quitter")
            choix = input("Choix : ").strip().lower()
 
            if choix == "0":
                run_one_test(ser)
            elif choix == "1":
                calib_results = run_calibration(ser)
                if calib_results:
                    print(f"\n{len(calib_results)} masses calibrées avec succès.")
                    print("Les valeurs brutes sont conservées pour linéarisation.")
            elif choix in {"q", "quit", "exit"}:
                break
            else:
                print("Choix invalide.")
                continue
            # ===== FIN AJOUT CALIBRATION — menu principal =====