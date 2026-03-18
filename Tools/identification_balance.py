from __future__ import annotations

import csv
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import matplotlib.pyplot as plt
import serial
from serial.tools import list_ports

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


def choose_serial_port() -> str:
    ports = list(list_ports.comports())

    if not ports:
        print("Aucun port série détecté automatiquement.")
        while True:
            port = input("Entre quand même le nom du port (ex: COM5 ou /dev/ttyACM0) : ").strip()
            if port:
                return port
            print("Entrée invalide. Le nom du port ne peut pas être vide.")

    print("Ports série détectés :")
    available = []
    for p in ports:
        available.append(p.device)
        description = f" - {p.description}" if p.description else ""
        print(f"  - {p.device}{description}")

    if len(available) == 1:
        only_port = available[0]
        if ask_yes_no(f"Utiliser automatiquement {only_port} ? (O/N) : "):
            return only_port

    available_lower = {p.lower(): p for p in available}
    while True:
        port = input("Entre exactement le port à utiliser : ").strip()
        if not port:
            print("Entrée invalide. Le nom du port ne peut pas être vide.")
            continue
        if port.lower() in available_lower:
            return available_lower[port.lower()]
        print("Port invalide. Choisis un port affiché dans la liste.")


def open_serial_port(port: str) -> serial.Serial:
    ser = serial.Serial(port=port, baudrate=BAUDRATE, timeout=0, write_timeout=1)
    time.sleep(ARDUINO_BOOT_DELAY_S)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    return ser


def wait_for_byte(ser: serial.Serial, expected: bytes, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        b = ser.read(1)
        if not b:
            time.sleep(0.001)
            continue
        if b == expected:
            return
    raise TimeoutError(f"Octet attendu non reçu: {expected!r}")


# IMPORTANT:
# Avec le protocole Arduino actuel, il faut enlever l'ACK 'D' dans le bloc cmd == 'P'
# de main_ident.cpp, sinon cet octet se mélange aux données binaires et casse la lecture.
def send_pwm(ser: serial.Serial, pwm_percent: int) -> None:
    if not (0 <= pwm_percent <= 100):
        raise ValueError("pwm_percent doit être entre 0 et 100")
    ser.write(bytes((ord('P'), pwm_percent)))
    ser.flush()


def send_start(ser: serial.Serial) -> None:
    ser.reset_input_buffer()
    ser.write(b'S')
    ser.flush()
    wait_for_byte(ser, b'O', timeout_s=0.5)


def send_stop(ser: serial.Serial) -> None:
    ser.write(b'E')
    ser.flush()
    time.sleep(0.05)
    ser.reset_input_buffer()


def pump_samples_from_serial(
    ser: serial.Serial,
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
    ser: serial.Serial,
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

    # Petite vidange pour récupérer les derniers octets déjà arrivés.
    flush_deadline = time.monotonic() + 0.02
    while time.monotonic() < flush_deadline:
        next_k = pump_samples_from_serial(ser, rx_buffer, samples, next_k, pwm_value)
        if ser.in_waiting == 0:
            time.sleep(SERIAL_POLL_SLEEP_S)

    return samples, next_k


def collect_test_phase(
    ser: serial.Serial,
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

    # Petite vidange pour récupérer les derniers octets déjà arrivés.
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


def run_one_test(ser: serial.Serial) -> None:
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


def main() -> None:
    ensure_data_dir()
    print(f"Dossier de données : {DATA_DIR}")
    print()

    port = choose_serial_port()
    ser = None

    try:
        ser = open_serial_port(port)
        print(f"Port ouvert : {port}")

        while True:
            run_one_test(ser)
            if not ask_yes_no("Veux-tu faire un autre test ? (O/N) : "):
                break

    except KeyboardInterrupt:
        print("\nArrêt demandé par l'utilisateur.")
    except serial.SerialException as e:
        print(f"Erreur série : {e}")
    except TimeoutError as e:
        print(f"Timeout : {e}")
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
