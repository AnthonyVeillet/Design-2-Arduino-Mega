import argparse
import time
from pathlib import Path

import numpy as np
import serial


def read_header(ser: serial.Serial, timeout_s: float = 3.0):
    """
    On lit les lignes #... jusqu'à #ENDHDR
    Retourne dict header.
    """
    ser.timeout = 0.2
    header = {}
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        line = ser.readline()
        if not line:
            continue
        try:
            s = line.decode("ascii", errors="ignore").strip()
        except Exception:
            continue

        if s.startswith("#FS_HZ="):
            header["fs_hz"] = int(s.split("=", 1)[1])
        elif s.startswith("#VREF_VOLTS="):
            header["vref_volts"] = float(s.split("=", 1)[1])
        elif s.startswith("#FORMAT="):
            header["format"] = s.split("=", 1)[1]
        elif s == "#ENDHDR":
            return header

    raise RuntimeError("Header not received (check baud rate / port / that you sent START).")


def capture_binary_samples(ser: serial.Serial, duration_s: float):
    """
    Read 2-byte little endian ADC samples for duration_s.
    """
    ser.timeout = 0.2
    raw = bytearray()
    t_end = time.time() + duration_s

    while time.time() < t_end:
        chunk = ser.read(4096)
        if chunk:
            raw.extend(chunk)

    # Keep even count
    if len(raw) % 2 == 1:
        raw = raw[:-1]

    data = np.frombuffer(raw, dtype=np.uint16)  # little endian on x86 ok
    return data.copy()


def adc_to_volts(adc: np.ndarray, vref: float) -> np.ndarray:
    return (adc.astype(np.float64) * vref) / 1023.0


def analyze_deltas(volts: np.ndarray, threshold_v: float, percentile: float):
    """
    Returns a verdict using a percentile criterion on abs(delta).
    Example: if P95(|ΔV|) < threshold => mostly too small changes.
    """
    if len(volts) < 2:
        return {"ok": False, "reason": "Not enough samples"}

    dv = np.abs(np.diff(volts))
    p = np.percentile(dv, percentile)
    mx = float(np.max(dv))
    mn = float(np.min(dv))
    med = float(np.median(dv))

    verdict = p < threshold_v
    return {
        "ok": True,
        "samples": int(len(volts)),
        "p_abs_dv": float(p),
        "max_abs_dv": mx,
        "min_abs_dv": mn,
        "median_abs_dv": med,
        "threshold_v": float(threshold_v),
        "percentile": float(percentile),
        "limit_reached": bool(verdict),
    }


def save_csv(path: Path, fs_hz: int, vref: float, adc: np.ndarray, volts: np.ndarray):
    # timestamps approximatifs basés sur fs
    t = np.arange(len(adc), dtype=np.float64) / float(fs_hz)
    header = [
        f"# FS_HZ={fs_hz}",
        f"# VREF_VOLTS={vref}",
        "# columns: t_s, adc_10bit, volts"
    ]
    arr = np.column_stack([t, adc.astype(np.int64), volts])
    np.savetxt(path, arr, delimiter=",", header="\n".join(header), comments="", fmt=["%.9f", "%d", "%.6f"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="COMx on Windows, /dev/ttyACM0 on Linux")
    ap.add_argument("--baud", type=int, default=2000000)
    ap.add_argument("--fs", type=int, required=True, help="Sampling frequency to set on Arduino (Hz)")
    ap.add_argument("--seconds", type=float, default=5.0, help="Capture duration")
    ap.add_argument("--outdir", default="captures")
    ap.add_argument("--threshold", type=float, default=0.005, help="Delta-V threshold (V)")
    ap.add_argument("--percentile", type=float, default=95.0, help="Percentile on |ΔV| used as criterion")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    filename = f"Echantillonnage{args.fs}.csv"
    outpath = outdir / filename

    with serial.Serial(args.port, args.baud) as ser:
        time.sleep(1.5)  # let Arduino reboot

        # set fs
        ser.write(f"FS={args.fs}\n".encode("ascii"))
        ser.flush()
        time.sleep(0.2)

        # start
        ser.reset_input_buffer()
        ser.write(b"START\n")
        ser.flush()

        header = read_header(ser)
        fs_hz = header.get("fs_hz", args.fs)
        vref = header.get("vref_volts", 5.0)

        adc = capture_binary_samples(ser, args.seconds)

        ser.write(b"STOP\n")
        ser.flush()

    volts = adc_to_volts(adc, vref)
    save_csv(outpath, fs_hz, vref, adc, volts)

    res = analyze_deltas(volts, args.threshold, args.percentile)

    print(f"\nSaved: {outpath}")
    if not res["ok"]:
        print("Analysis failed:", res["reason"])
        return

    print("\n--- Analysis ---")
    print(f"Samples: {res['samples']}")
    print(f"Median |ΔV|: {res['median_abs_dv']:.6f} V")
    print(f"P{res['percentile']:.0f} |ΔV|: {res['p_abs_dv']:.6f} V")
    print(f"Max |ΔV|: {res['max_abs_dv']:.6f} V")
    print(f"Threshold: {res['threshold_v']:.6f} V")

    if res["limit_reached"]:
        print("\n⚠️  LIMIT REACHED: variations mostly below threshold -> ADC changes are too small at this fs.")
    else:
        print("\n✅ OK: variations still above threshold often enough -> you can try increasing fs.")


if __name__ == "__main__":
    main()
