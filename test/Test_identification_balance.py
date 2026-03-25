from __future__ import annotations

import csv
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import matplotlib.pyplot as plt
# ===== DÉBUT MODIFICATION TEST — import fake serial =====
# import serial
# from serial.tools import list_ports
from fake_serial import FakeSerial
# ===== FIN MODIFICATION TEST — import fake serial =====

BAUDRATE = 115200
SAMPLE_RATE_HZ = 500.0
REF_DURATION_S = 5.0
STEP_ON_DURATION_S = 15.0
PULSE_ON_DURATION_S = 0.050
POST_ZERO_DURATION_S = 15.0
ARDUINO_BOOT_DELAY_S = 2.0
SERIAL_POLL_SLEEP_S = 0.0005

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "dataIdentification"


@dataclass
class Sample:
    k: int
    pwm: int
    position: int
    courant: int


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def ask_yes_no(prompt: str) -> bool:
    while True:
        value = input(prompt).strip().lower()
        if value in {"o", "oui", "y", "yes"}:
            return True
        if value in {"n", "non", "no"}:
            return False
        print("Entrée invalide. Réponds par O ou N.")


def ask_int_in_range(prompt: str, min_value: int, max_value: int) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            value = int(raw)
        except ValueError:
            print("Entrée invalide. Entre un nombre entier.")
            continue

        if min_value <= value <= max_value:
            return value

        print(f"Entrée invalide. La valeur doit être entre {min_value} et {max_value}.")


def ask_test_type() -> Tuple[str, str, float]:
    while True:
        value = input("Quel test veux-tu faire ? (0 = Échelon, 1 = Impulsion courte) : ").strip()
        if value == "0":
            return "Échelon", "Echelon", STEP_ON_DURATION_S
        if value == "1":
            return "Impulsion courte", "ImpulsionCourte", PULSE_ON_DURATION_S
        print("Entrée invalide. Entre 0 ou 1.")


# ===== DÉBUT MODIFICATION TEST — choose_serial_port remplacé =====
def choose_serial_port() -> str:
    """En mode test, retourne toujours 'FAKE'."""
    print("MODE TEST : utilisation du port série simulé (FakeSerial)")
    return "FAKE"
# ===== FIN MODIFICATION TEST — choose_serial_port remplacé =====


# ===== DÉBUT MODIFICATION TEST — open_serial_port remplacé =====
def open_serial_port(port: str) -> FakeSerial:
    """En mode test, crée un FakeSerial au lieu de serial.Serial."""
    ser = FakeSerial(port=port, baudrate=BAUDRATE)
    time.sleep(0.2)  # Pas besoin d'attendre 2s
    return ser
# ===== FIN MODIFICATION TEST — open_serial_port remplacé =====


def wait_for_byte(ser, expected: bytes, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        b = ser.read(1)
        if not b:
            time.sleep(0.001)
            continue
        if b == expected:
            return
    raise TimeoutError(f"Octet attendu non reçu: {expected!r}")


def send_pwm(ser, pwm_percent: int) -> None:
    if not (0 <= pwm_percent <= 100):
        raise ValueError("pwm_percent doit être entre 0 et 100")
    ser.write(bytes((ord('P'), pwm_percent)))
    ser.flush()


def send_start(ser) -> None:
    ser.reset_input_buffer()
    ser.write(b'S')
    ser.flush()
    wait_for_byte(ser, b'O', timeout_s=0.5)


def send_stop(ser) -> None:
    ser.write(b'E')
    ser.flush()
    time.sleep(0.05)
    ser.reset_input_buffer()


def pump_samples_from_serial(
    ser,
    rx_buffer: bytearray,
    samples: List[Sample],
    next_k: int,
    current_pwm: int,
) -> int:
    waiting = ser.in_waiting
    if waiting > 0:
        rx_buffer.extend(ser.read(waiting))

    while len(rx_buffer) >= 4:
        position, courant = struct.unpack_from('<HH', rx_buffer, 0)
        del rx_buffer[:4]
        samples.append(Sample(k=next_k, pwm=current_pwm, position=position, courant=courant))
        next_k += 1

    return next_k


def collect_constant_phase(
    ser,
    duration_s: float,
    start_k: int,
    pwm_value: int,
) -> Tuple[List[Sample], int]:
    samples: List[Sample] = []
    rx_buffer = bytearray()
    next_k = start_k
    deadline = time.monotonic() + duration_s

    while time.monotonic() < deadline:
        next_k = pump_samples_from_serial(ser, rx_buffer, samples, next_k, pwm_value)
        if ser.in_waiting == 0:
            time.sleep(SERIAL_POLL_SLEEP_S)

    flush_deadline = time.monotonic() + 0.02
    while time.monotonic() < flush_deadline:
        next_k = pump_samples_from_serial(ser, rx_buffer, samples, next_k, pwm_value)
        if ser.in_waiting == 0:
            time.sleep(SERIAL_POLL_SLEEP_S)

    return samples, next_k


def collect_test_phase(
    ser,
    on_duration_s: float,
    post_zero_s: float,
    start_k: int,
    pwm_on: int,
) -> Tuple[List[Sample], int]:
    samples: List[Sample] = []
    rx_buffer = bytearray()
    next_k = start_k

    send_pwm(ser, pwm_on)
    current_pwm = pwm_on
    start = time.monotonic()
    zero_sent = False
    total_duration = on_duration_s + post_zero_s

    while True:
        elapsed = time.monotonic() - start

        if (not zero_sent) and (elapsed >= on_duration_s):
            send_pwm(ser, 50)
            current_pwm = 50
            zero_sent = True

        next_k = pump_samples_from_serial(ser, rx_buffer, samples, next_k, current_pwm)

        if elapsed >= total_duration:
            break

        if ser.in_waiting == 0:
            time.sleep(SERIAL_POLL_SLEEP_S)

    flush_deadline = time.monotonic() + 0.02
    while time.monotonic() < flush_deadline:
        next_k = pump_samples_from_serial(ser, rx_buffer, samples, next_k, current_pwm)
        if ser.in_waiting == 0:
            time.sleep(SERIAL_POLL_SLEEP_S)

    return samples, next_k


def compute_references(samples: List[Sample]) -> Tuple[float, float]:
    if not samples:
        raise RuntimeError("Aucune donnée reçue pendant le tarage de 5 secondes.")

    position_ref = sum(s.position for s in samples) / len(samples)
    courant_ref = sum(s.courant for s in samples) / len(samples)
    return position_ref, courant_ref


def write_csv(
    csv_path: Path,
    all_samples: List[Sample],
    pwm_test_value: int,
    position_ref: float,
    courant_ref: float,
) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "k",
            "time_s",
            "pwmVal",
            "position",
            "courant",
            "positionRef",
            "courantRef",
            "positionReel",
            "courantReel",
        ])

        for s in all_samples:
            time_s = s.k / SAMPLE_RATE_HZ
            position_reel = s.position - position_ref
            courant_reel = s.courant - courant_ref
            writer.writerow([
                s.k,
                f"{time_s:.6f}",
                s.pwm,
                s.position,
                s.courant,
                f"{position_ref:.6f}",
                f"{courant_ref:.6f}",
                f"{position_reel:.6f}",
                f"{courant_reel:.6f}",
            ])


def plot_and_save(
    png_path: Path,
    all_samples: List[Sample],
    test_label: str,
    pwm_test_value: int,
    position_ref: float,
    courant_ref: float,
) -> None:
    times = [s.k / SAMPLE_RATE_HZ for s in all_samples]
    position_reel = [s.position - position_ref for s in all_samples]
    courant_reel = [s.courant - courant_ref for s in all_samples]

    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(11, 7))

    ax1.plot(times, position_reel)
    ax1.set_ylabel("positionReel")
    ax1.grid(True)

    ax2.plot(times, courant_reel)
    ax2.set_xlabel("Temps (s)")
    ax2.set_ylabel("courantReel")
    ax2.grid(True)

    fig.suptitle(f"{test_label} - PWM {pwm_test_value}%")
    fig.tight_layout()
    fig.savefig(png_path, dpi=150)
    print(f"Graphique enregistré : {png_path}")
    plt.show()


def run_one_test(ser) -> None:
    send_pwm(ser, 50)
    time.sleep(0.05)
    ser.reset_input_buffer()

    test_label, test_name_file, on_duration_s = ask_test_type()
    pwm_value = ask_int_in_range(
        "Quel pourcentage de PWM veux-tu envoyer (0 à 100) ? : ",
        0,
        100,
    )

    is_ready = ask_yes_no(
        "La balance est-elle bien au repos et en régime permanent ? (O/N) : "
    )
    if not is_ready:
        print(
            "Place la balance au repos et n'applique aucune force sur ses composantes, "
            "puis relance le script."
        )
        return

    print(
        "Tarage de la position et du courant de référence en cours (5 secondes)...\n"
        "Une fois terminé, ne pas modifier le prototype."
    )

    print(f"Test {test_label} avec un PWM de {pwm_value}%")

    send_start(ser)
    ref_samples, next_k = collect_constant_phase(
        ser=ser,
        duration_s=REF_DURATION_S,
        start_k=0,
        pwm_value=50,
    )
    send_stop(ser)

    send_start(ser)
    test_samples, _ = collect_test_phase(
        ser=ser,
        on_duration_s=on_duration_s,
        post_zero_s=POST_ZERO_DURATION_S,
        start_k=next_k,
        pwm_on=pwm_value,
    )
    send_stop(ser)
    send_pwm(ser, 50)
    time.sleep(0.05)
    ser.reset_input_buffer()

    position_ref, courant_ref = compute_references(ref_samples)
    print(f"positionRef = {position_ref:.6f}")
    print(f"courantRef  = {courant_ref:.6f}")

    csv_path = DATA_DIR / f"{test_name_file}_{pwm_value}.csv"
    png_path = DATA_DIR / f"{test_name_file}_{pwm_value}.png"

    all_samples = ref_samples + test_samples

    write_csv(
        csv_path=csv_path,
        all_samples=all_samples,
        pwm_test_value=pwm_value,
        position_ref=position_ref,
        courant_ref=courant_ref,
    )
    print(f"Données enregistrées : {csv_path}")

    plot_and_save(
        png_path=png_path,
        all_samples=all_samples,
        test_label=test_label,
        pwm_test_value=pwm_value,
        position_ref=position_ref,
        courant_ref=courant_ref,
    )


# ===== DÉBUT AJOUT CALIBRATION — constantes =====
CALIB_TARE_DURATION_S = 5.0
CALIB_MEASURE_DURATION_S = 3.0
CALIB_DATA_DIR = BASE_DIR / "dataCalibration"
# ===== FIN AJOUT CALIBRATION — constantes =====


# ===== DÉBUT AJOUT CALIBRATION — fonctions =====

@dataclass
class CalibrationResult:
    num: int
    masse_reelle: float
    courant_raw: float
    courant_ref: float
    delta_raw: float
    courant_amperes: float


def collect_calib_samples(
    ser,
    duration_s: float,
) -> List[int]:
    """Collecte les valeurs brutes de courant pendant une durée donnée.

    Note : Le FakeSerial envoie des paquets 'T' (9 octets). Ici on utilise
    le protocole d'acquisition (paquets de 4 octets bruts) envoyé quand
    acquisitionActive est true. Avec le FakeSerial, on parse les paquets 'T'
    pour extraire le courant.
    """
    rx_buffer = bytearray()
    courant_values: List[int] = []
    deadline = time.monotonic() + duration_s

    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting > 0:
            rx_buffer.extend(ser.read(waiting))

        # Le FakeSerial envoie des paquets 'T' + 8 octets (comme main.cpp loop)
        # On parse ces paquets pour en extraire le courant
        while len(rx_buffer) >= 9:
            if rx_buffer[0] == ord('T'):
                _pos, courant, _cmd_pos, _cmd_cur = struct.unpack_from('<HHHH', rx_buffer, 1)
                del rx_buffer[:9]
                courant_values.append(courant)
            else:
                # Skip un octet inconnu
                del rx_buffer[0]

        if ser.in_waiting == 0:
            time.sleep(SERIAL_POLL_SLEEP_S)

    # Vidange finale
    flush_deadline = time.monotonic() + 0.05
    while time.monotonic() < flush_deadline:
        waiting = ser.in_waiting
        if waiting > 0:
            rx_buffer.extend(ser.read(waiting))
        while len(rx_buffer) >= 9:
            if rx_buffer[0] == ord('T'):
                _pos, courant, _cmd_pos, _cmd_cur = struct.unpack_from('<HHHH', rx_buffer, 1)
                del rx_buffer[:9]
                courant_values.append(courant)
            else:
                del rx_buffer[0]
        if ser.in_waiting == 0:
            time.sleep(SERIAL_POLL_SLEEP_S)

    return courant_values


def convert_raw_to_amperes(delta_raw: float, adc_bits: int) -> float:
    adc_max = (2 ** adc_bits) - 1
    plage_courant = 3.0
    return delta_raw * plage_courant / adc_max


def write_calib_csv(csv_path: Path, results: List[CalibrationResult]) -> None:
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


def run_calibration(ser) -> List[CalibrationResult]:
    CALIB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    num_masses = ask_int_in_range(
        "Combien de masses de calibration ? : ", 1, 50
    )
    adc_bits = ask_int_in_range(
        "Nombre de bits de l'ADC ? : ", 8, 16
    )

    ser.write(b'N')
    ser.flush()
    time.sleep(0.05)

    is_ready = ask_yes_no(
        "La balance est-elle au repos, SANS aucune masse ? (O/N) : "
    )
    if not is_ready:
        print("Place la balance au repos sans masse, puis relance la calibration.")
        return []

    print(f"\nTare de calibration en cours ({CALIB_TARE_DURATION_S} secondes)...")
    print("Ne pas toucher à la balance.")

    # ===== DÉBUT MODIFICATION TEST — pas de send_start pour tare =====
    # Le FakeSerial envoie des 'T' en continu, pas besoin de send_start
    tare_values = collect_calib_samples(ser, CALIB_TARE_DURATION_S)
    # ===== FIN MODIFICATION TEST =====

    if not tare_values:
        print("Erreur : aucune donnée reçue pendant le tare.")
        return []

    courant_ref = sum(tare_values) / len(tare_values)
    print(f"courantRef = {courant_ref:.6f} ({len(tare_values)} échantillons)")

    masses_reelles: List[float] = [0.0] * num_masses
    courants_raw: List[float] = [0.0] * num_masses

    index = 0
    while index < num_masses:
        print(f"\n--- Masse {index + 1} / {num_masses} ---")
        print("Place la masse de calibration sur la balance.")

        # ===== DÉBUT MODIFICATION TEST — simulation masse =====
        print("  [TEST] Pour simuler une masse, le FakeSerial utilise un")
        print("  décalage de courant. Tu peux appeler ser.simulate_add_mass(N)")
        print("  ou simplement continuer (le courant sera ~512 ± bruit).")
        # ===== FIN MODIFICATION TEST =====

        while True:
            raw_input_val = input(f"Valeur réelle de la masse {index + 1} (en grammes) : ").strip()
            try:
                masse_val = float(raw_input_val)
                break
            except ValueError:
                print("Entrée invalide. Entre un nombre.")

        masses_reelles[index] = masse_val

        # ===== DÉBUT MODIFICATION TEST — simuler offset masse =====
        sim_offset = ask_int_in_range(
            f"[TEST] Décalage courant à simuler pour cette masse (0–200) : ", 0, 200
        )
        ser.simulate_add_mass(sim_offset)
        time.sleep(0.1)  # Laisser quelques paquets avec le nouvel offset
        # ===== FIN MODIFICATION TEST =====

        input("Appuie sur Entrée quand la balance est stable pour lancer l'acquisition...")

        print(f"Acquisition en cours ({CALIB_MEASURE_DURATION_S} secondes)...")
        values = collect_calib_samples(ser, CALIB_MEASURE_DURATION_S)

        # ===== DÉBUT MODIFICATION TEST — retirer masse simulée =====
        ser.simulate_remove_mass()
        # ===== FIN MODIFICATION TEST =====

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

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    csv_path = CALIB_DATA_DIR / f"calibration_{timestamp}.csv"
    write_calib_csv(csv_path, results)
    print(f"\nRésultats enregistrés : {csv_path}")

    return results

# ===== FIN AJOUT CALIBRATION — fonctions =====


def main() -> None:
    ensure_data_dir()
    print(f"Dossier de données : {DATA_DIR}")
    print()
    print("=" * 50)
    print("  MODE TEST — Arduino simulé (FakeSerial)")
    print("=" * 50)
    print()

    port = choose_serial_port()
    ser = None

    try:
        ser = open_serial_port(port)
        print(f"Port ouvert : {port}")

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

    except KeyboardInterrupt:
        print("\nArrêt demandé par l'utilisateur.")
    except Exception as e:
        print(f"Erreur : {e}")
    finally:
        if ser is not None:
            try:
                send_pwm(ser, 50)
                time.sleep(0.05)
                send_stop(ser)
            except Exception:
                pass
            try:
                ser.close()
            except Exception:
                pass
        plt.close('all')


if __name__ == "__main__":
    main()
