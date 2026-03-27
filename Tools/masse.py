"""
masse.py — Logique de calibration de la balance.
"""

import json
import threading
import time
from pathlib import Path

# ── Constantes ──────────────────────────────────────────────────────────────
ADC_BITS = 10
ADC_MAX = 2**ADC_BITS - 1          # 1023
V_REF = 5.0                        # Plage de lecture 0 – 5 V

BASE_DIR = Path(__file__).resolve().parent
CALIBRATION_DIR = BASE_DIR / "dataCalibration"

# ── État de la calibration (variables de module) ────────────────────────────
num_masses = 0
averaging_time_ms = 2000
current_index = 0
nextMasse = False

# Fonctions fournies par ui.py au démarrage
_get_courant = None
_get_flag = None

# Résultats : liste de dicts {numero, masse_g, adc_moyen, tension_v} ou None
results = []

# Variables internes de collecte
_accumulator = []
_collecting = False
_collect_thread = None
_cur_moyen = 0.0
_lock = threading.Lock()


# ── Conversion ADC → tension ────────────────────────────────────────────────
def adc_to_voltage(adc_val):
    return (adc_val / ADC_MAX) * V_REF


# ── Initialisation ──────────────────────────────────────────────────────────
def init_calibration(n_masses, avg_time_ms, get_courant_fn, get_flag_fn):
    global num_masses, averaging_time_ms, current_index, nextMasse
    global results, _get_courant, _get_flag
    global _accumulator, _collecting, _collect_thread, _cur_moyen

    num_masses = n_masses
    averaging_time_ms = max(avg_time_ms, 1000)
    current_index = 0
    nextMasse = False

    _get_courant = get_courant_fn
    _get_flag = get_flag_fn

    results = [None] * num_masses
    _accumulator = []
    _collecting = False
    _collect_thread = None
    _cur_moyen = 0.0


# ── Collecte (nextMasse logic) ──────────────────────────────────────────────
def start_next_masse():
    global nextMasse, _accumulator, _cur_moyen, _collecting, _collect_thread

    nextMasse = False
    _accumulator = []
    _cur_moyen = 0.0
    _collecting = True
    _collect_thread = threading.Thread(target=_collect_loop, daemon=True)
    _collect_thread.start()


def stop_collecting():
    global _collecting, _collect_thread

    _collecting = False
    if _collect_thread is not None:
        _collect_thread.join(timeout=1.0)
        _collect_thread = None


def _collect_loop():
    global nextMasse, _cur_moyen

    # Étape 1 : attendre flag == True (balance stabilisée)
    while _collecting:
        if _get_flag():
            break
        time.sleep(0.005)

    if not _collecting:
        return

    # Étape 2 : accumuler pendant le délai de moyennage
    delay_s = averaging_time_ms / 1000.0
    start = time.monotonic()

    while _collecting:
        val = _get_courant()
        with _lock:
            _accumulator.append(val)
        time.sleep(0.002)

        if time.monotonic() - start >= delay_s:
            with _lock:
                if _accumulator:
                    _cur_moyen = sum(_accumulator) / len(_accumulator)
            nextMasse = True
            break

    # Étape 3 : continuer d'accumuler jusqu'à stop_collecting()
    while _collecting:
        val = _get_courant()
        with _lock:
            _accumulator.append(val)
            _cur_moyen = sum(_accumulator) / len(_accumulator)
        time.sleep(0.002)


def get_cur_moyen():
    with _lock:
        return _cur_moyen


# ── Navigation ──────────────────────────────────────────────────────────────
def validate_current(masse_reelle_g):
    global current_index, nextMasse

    stop_collecting()

    tension = adc_to_voltage(_cur_moyen)
    result = {
        "numero": current_index + 1,
        "masse_g": masse_reelle_g,
        "adc_moyen": _cur_moyen,
        "tension_v": tension,
    }
    results[current_index] = result
    current_index += 1
    nextMasse = False
    return result


def go_previous():
    global current_index, nextMasse

    stop_collecting()
    nextMasse = False
    if current_index > 0:
        current_index -= 1
        results[current_index] = None


def is_last_mass():
    return current_index >= num_masses - 1


def is_done():
    return current_index >= num_masses


# ── Sauvegarde ──────────────────────────────────────────────────────────────
def save_calibration():
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)

    cal_dict = {}
    for r in results:
        if r is not None:
            cal_dict[str(r["masse_g"])] = r["tension_v"]

    cal_path = CALIBRATION_DIR / "calibration.json"
    with open(cal_path, "w", encoding="utf-8") as f:
        json.dump(cal_dict, f, indent=2, ensure_ascii=False)

    return cal_path


def get_valid_results():
    return [r for r in results if r is not None]


# ── Fonctions TODO ──────────────────────────────────────────────────────────
def interpolation(cal_dict):
    """TODO"""
    pass


def convert_to_masse(tension, cal_dict):
    """TODO"""
    pass