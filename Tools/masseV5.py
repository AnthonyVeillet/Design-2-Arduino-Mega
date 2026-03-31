"""
masse.py — Logique de calibration et conversion de la balance.
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

# ===== DÉBUT AJOUT — mode calibration vs mesure =====
_calibration_mode = True
# ===== FIN AJOUT — mode calibration vs mesure =====


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


# ===== DÉBUT AJOUT — init_measurement pour usage hors calibration =====
def init_measurement(avg_time_ms, get_courant_fn, get_flag_fn):
    """
    Initialise les fonctions de lecture sans toucher à l'état de calibration.
    Utilisé pour start_next_masse(calibration_mode=False) hors calibration.
    """
    global averaging_time_ms, _get_courant, _get_flag

    averaging_time_ms = max(avg_time_ms, 1000)
    _get_courant = get_courant_fn
    _get_flag = get_flag_fn
# ===== FIN AJOUT — init_measurement =====


# ── Collecte (nextMasse logic) ──────────────────────────────────────────────

# ===== DÉBUT MODIFICATION — start_next_masse avec paramètre calibration_mode =====
def start_next_masse(calibration_mode=True):
    """
    Lance la collecte de la prochaine mesure.
    
    calibration_mode=True  → la collecte continue après le délai de moyennage
                             jusqu'à ce que l'utilisateur appuie sur Next (stop_collecting).
    calibration_mode=False → la collecte s'arrête automatiquement après le délai
                             de moyennage. Utilisé pour la mesure continue (hors calibration).
    """
    global nextMasse, _accumulator, _cur_moyen, _collecting, _collect_thread
    global _calibration_mode

    _calibration_mode = calibration_mode
    nextMasse = False
    _accumulator = []
    _cur_moyen = 0.0
    _collecting = True
    _collect_thread = threading.Thread(target=_collect_loop, daemon=True)
    _collect_thread.start()
# ===== FIN MODIFICATION — start_next_masse =====


def stop_collecting():
    global _collecting, _collect_thread

    _collecting = False
    if _collect_thread is not None:
        _collect_thread.join(timeout=1.0)
        _collect_thread = None


# ===== DÉBUT MODIFICATION — _collect_loop avec gestion calibration_mode =====
def _collect_loop():
    global nextMasse, _cur_moyen, _collecting

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

    # Étape 3 : comportement selon le mode
    if _calibration_mode:
        # Mode calibration : continuer d'accumuler jusqu'à stop_collecting()
        # (l'utilisateur doit appuyer sur Next)
        while _collecting:
            val = _get_courant()
            with _lock:
                _accumulator.append(val)
                _cur_moyen = sum(_accumulator) / len(_accumulator)
            time.sleep(0.002)
    else:
        # Mode mesure : la collecte s'arrête automatiquement
        _collecting = False
# ===== FIN MODIFICATION — _collect_loop =====


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


# ── Sauvegarde et chargement ────────────────────────────────────────────────
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


# ===== DÉBUT AJOUT — load_calibration =====
def load_calibration():
    """
    Charge le fichier calibration.json et retourne le dictionnaire
    {masse_g_str: tension_v} ou None si le fichier n'existe pas.
    """
    cal_path = CALIBRATION_DIR / "calibration.json"
    if not cal_path.exists():
        return None
    try:
        with open(cal_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
# ===== FIN AJOUT — load_calibration =====


def get_valid_results():
    return [r for r in results if r is not None]


# ===== DÉBUT AJOUT — Modèles de calibration et convertMasse =====

# ── Ajustement par moindres carrés (modèle affine) ──────────────────────────
def _fit_affine(voltages, masses):
    """
    Ajustement affine par moindres carrés : m = a*V + b
    Retourne (a, b).
    Réf: eq. 7.39 et 7.40 du document de design.
    """
    n = len(voltages)
    sum_v = sum(voltages)
    sum_m = sum(masses)
    sum_vv = sum(v * v for v in voltages)
    sum_vm = sum(v * m for v, m in zip(voltages, masses))

    denom = n * sum_vv - sum_v * sum_v
    if abs(denom) < 1e-12:
        # Points tous au même voltage → impossible de fitter
        return 0.0, sum_m / n if n > 0 else 0.0

    a = (n * sum_vm - sum_v * sum_m) / denom
    b = (sum_m - a * sum_v) / n
    return a, b


# ── Ajustement par moindres carrés (modèle quadratique) ─────────────────────
def _fit_quadratic(voltages, masses):
    """
    Ajustement quadratique par moindres carrés : m = a2*V² + a1*V + a0
    Retourne (a2, a1, a0).
    Réf: eq. 6.32 du document de design.
    Résolution du système normal 3×3 par élimination de Gauss.
    """
    n = len(voltages)
    # Construire les sommes pour le système normal A^T A x = A^T b
    s0 = float(n)
    s1 = sum(voltages)
    s2 = sum(v**2 for v in voltages)
    s3 = sum(v**3 for v in voltages)
    s4 = sum(v**4 for v in voltages)

    t0 = sum(masses)
    t1 = sum(v * m for v, m in zip(voltages, masses))
    t2 = sum(v**2 * m for v, m in zip(voltages, masses))

    # Système :
    # | s0  s1  s2 | | a0 |   | t0 |
    # | s1  s2  s3 | | a1 | = | t1 |
    # | s2  s3  s4 | | a2 |   | t2 |

    mat = [
        [s0, s1, s2, t0],
        [s1, s2, s3, t1],
        [s2, s3, s4, t2],
    ]

    # Élimination de Gauss avec pivot partiel
    for col in range(3):
        # Pivot partiel
        max_row = col
        for row in range(col + 1, 3):
            if abs(mat[row][col]) > abs(mat[max_row][col]):
                max_row = row
        mat[col], mat[max_row] = mat[max_row], mat[col]

        if abs(mat[col][col]) < 1e-12:
            continue

        for row in range(col + 1, 3):
            factor = mat[row][col] / mat[col][col]
            for j in range(col, 4):
                mat[row][j] -= factor * mat[col][j]

    # Substitution arrière
    x = [0.0, 0.0, 0.0]
    for i in range(2, -1, -1):
        if abs(mat[i][i]) < 1e-12:
            x[i] = 0.0
            continue
        x[i] = mat[i][3]
        for j in range(i + 1, 3):
            x[i] -= mat[i][j] * x[j]
        x[i] /= mat[i][i]

    a0, a1, a2 = x
    return a2, a1, a0


# ── Interpolation linéaire par morceaux ─────────────────────────────────────
def _interpolate_piecewise(voltage, voltages, masses):
    """
    Interpolation linéaire par morceaux entre les points de calibration.
    Les points sont triés par voltage croissant.
    Extrapolation linéaire si hors de la plage.
    """
    # Trier par voltage
    pairs = sorted(zip(voltages, masses), key=lambda p: p[0])
    vs = [p[0] for p in pairs]
    ms = [p[1] for p in pairs]

    n = len(vs)
    if n == 0:
        return 0.0
    if n == 1:
        return ms[0]

    # Extrapolation basse (avant le premier point)
    if voltage <= vs[0]:
        slope = (ms[1] - ms[0]) / (vs[1] - vs[0]) if vs[1] != vs[0] else 0.0
        return ms[0] + slope * (voltage - vs[0])

    # Extrapolation haute (après le dernier point)
    if voltage >= vs[-1]:
        slope = (ms[-1] - ms[-2]) / (vs[-1] - vs[-2]) if vs[-1] != vs[-2] else 0.0
        return ms[-1] + slope * (voltage - vs[-1])

    # Trouver l'intervalle contenant voltage
    for i in range(n - 1):
        if vs[i] <= voltage <= vs[i + 1]:
            dv = vs[i + 1] - vs[i]
            if abs(dv) < 1e-12:
                return (ms[i] + ms[i + 1]) / 2.0
            t = (voltage - vs[i]) / dv
            return ms[i] + t * (ms[i + 1] - ms[i])

    return ms[-1]


# ── Calcul des résidus ──────────────────────────────────────────────────────
def compute_residuals(cal_dict, model="affine"):
    """
    Calcule les résidus r_i = m_i - m_hat_i pour le modèle choisi.
    Retourne une liste de résidus.
    """
    voltages, masses = _parse_cal_dict(cal_dict)
    if len(voltages) < 2:
        return []

    residuals = []
    for v, m in zip(voltages, masses):
        m_hat = _evaluate_model(v, voltages, masses, model)
        residuals.append(m - m_hat)
    return residuals


def _parse_cal_dict(cal_dict):
    """Convertit le dictionnaire {masse_g_str: tension_v} en listes (voltages, masses)."""
    voltages = []
    masses = []
    for masse_str, tension in cal_dict.items():
        masses.append(float(masse_str))
        voltages.append(float(tension))
    return voltages, masses


def _evaluate_model(voltage, voltages, masses, model):
    """Évalue le modèle de calibration pour une tension donnée."""
    if model == "affine":
        a, b = _fit_affine(voltages, masses)
        return a * voltage + b
    elif model == "quadratic":
        a2, a1, a0 = _fit_quadratic(voltages, masses)
        return a2 * voltage**2 + a1 * voltage + a0
    elif model == "piecewise":
        return _interpolate_piecewise(voltage, voltages, masses)
    else:
        return 0.0


# ── Fonction principale de conversion ───────────────────────────────────────
def convert_masse(adc_val, cal_dict, model="affine"):
    """
    Convertit une valeur ADC en masse (grammes) en utilisant le modèle
    de calibration spécifié.
    
    Paramètres :
      adc_val  — valeur numérique ADC (sortie de get_cur_moyen / nextMasse)
      cal_dict — dictionnaire {masse_g_str: tension_v} (calibration.json)
      model    — "affine", "quadratic" ou "piecewise"
    
    Retourne la masse en grammes, arrondie à 0.1 g.
    
    Réf: sections 6.4.3, 7.4.3, 7.4.4 du document de design.
    """
    if cal_dict is None or len(cal_dict) < 2:
        return 0.0

    voltage = adc_to_voltage(adc_val)
    voltages, masses = _parse_cal_dict(cal_dict)

    masse_g = _evaluate_model(voltage, voltages, masses, model)

    return round(masse_g, 1)

# ===== FIN AJOUT — Modèles de calibration et convertMasse =====