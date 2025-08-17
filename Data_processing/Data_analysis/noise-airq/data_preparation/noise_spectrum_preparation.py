#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, struct, time, math, yaml
from pathlib import Path
import numpy as np
import pandas as pd
from multiprocessing import Pool, cpu_count

# ===================== CONFIG (edit) =====================
INPUT_DIRS = [
    r"Z:\URV\UNIVER\5_2\TFG_1\EXPERIMENT_DATA\Noise_2"
]
KIT_CODE    = "NOISE102"
YAML_PATH   = r"config\time_window_unified.yaml"
OUT_PARQ    = r"data\processed\noise_voice_1min.parquet"
# ========================================================

# ====== Analysis config
VOICE_MIN_HZ, VOICE_MAX_HZ = 100.0, 4000.0
EPS = 1e-12

SNR_MIN_LINEAR    = 1.6
SFM_MAX_FOR_VOICE = 0.55
RISE_DB_OVER_BASE = 3.0
BASELINE_ALPHA    = 0.05
CONFIRM_FRAMES    = 2

W_RISE, W_SNR, W_HARM = 0.5, 0.3, 0.2

PARALLEL  = True
N_WORKERS = max(1, min(cpu_count(), 8))

# Safety clamps
NOISE_RMS_FLOOR = 1e-6
SNR_CAP         = 1e4

pd.set_option("mode.copy_on_write", True)

# =================== BIN parsing constants ===================
SECTOR   = 512
HDR_FMT  = "<4sQ B f f H f H 3s"   # magic,ts,voice,snr,energy,peaks,contrast,bins,res
HDR_SIZE = struct.calcsize(HDR_FMT)

def aligned_up(n, a=SECTOR):
    return ((n + a - 1) // a) * a

def load_window(yaml_file):
    with open(yaml_file, "r") as f:
        cfg = yaml.safe_load(f)
    return (int(cfg["window"]["epoch_utc"]["start"]),
            int(cfg["window"]["epoch_utc"]["end"]),
            cfg.get("timezone", "Europe/Madrid"))

def find_log_files(input_dir):
    files = []
    rx = re.compile(r"^LOG_(\d{4})\.BIN$", re.IGNORECASE)
    try:
        for name in os.listdir(input_dir):
            m = rx.match(name)
            if m:
                idx = int(m.group(1))
                files.append((idx, os.path.join(input_dir, name)))
    except FileNotFoundError:
        pass
    files.sort(key=lambda x: x[0])
    return files

# =================== Streaming aggregator ===================
def stream_frames_to_summaries(input_dirs, kit_code, start_ep, end_ep):
    rows = []
    next_frame_id = 0

    for idir in input_dirs:
        logs = find_log_files(idir)
        if not logs:
            print(f"[WARN] No LOG_*.BIN files found in {idir}")
            continue

        for _, path in logs:
            size = os.path.getsize(path)
            file_name = os.path.basename(path)
            print(f"[INFO] Parsing {file_name} ... size={size/1e6:.2f} MB")
            with open(path, "rb") as f:
                offset = 0
                while offset + HDR_SIZE <= size:
                    f.seek(offset)
                    hdr = f.read(HDR_SIZE)
                    if len(hdr) < HDR_SIZE:
                        break
                    magic, ts, voice, snr, energy, peaks, contrast, bins, _res = struct.unpack(HDR_FMT, hdr)

                    if magic != b"FFT2":
                        offset += SECTOR
                        continue

                    data_bytes = bins * 8
                    payload = f.read(data_bytes)
                    if len(payload) < data_bytes:
                        break

                    # window filter (half-open [start, end))
                    if ts < start_ep or ts >= end_ep:
                        raw_size = HDR_SIZE + data_bytes
                        offset += aligned_up(raw_size, SECTOR)
                        continue

                    # ---- Vectorized parse of (freq, mag) pairs ----
                    arr = np.frombuffer(payload, dtype="<f4")  # little-endian float32
                    if arr.size != bins * 2:
                        # corrupted frame; skip safely
                        raw_size = HDR_SIZE + data_bytes
                        offset += aligned_up(raw_size, SECTOR)
                        continue
                    arr = arr.reshape(-1, 2)
                    freqs = arr[:, 0]
                    mags  = arr[:, 1].astype(np.float64, copy=False)

                    in_band = (freqs >= VOICE_MIN_HZ) & (freqs <= VOICE_MAX_HZ)

                    sum_all  = float(np.sum(mags * mags, dtype=np.float64))
                    n_all    = int(mags.size)
                    m_band   = mags[in_band]
                    sum_band = float(np.sum(m_band * m_band, dtype=np.float64))
                    n_band   = int(m_band.size)

                    sum_mag_band     = float(np.sum(m_band, dtype=np.float64))
                    sum_log_mag_band = float(np.sum(np.log(np.maximum(m_band, EPS)), dtype=np.float64))

                    if n_all  == 0: n_all  = 1
                    if n_band == 0: n_band = 1

                    rows.append((
                        kit_code, file_name, next_frame_id, int(ts),
                        sum_band, sum_all, n_band, n_all,
                        sum_mag_band, sum_log_mag_band
                    ))
                    next_frame_id += 1

                    raw_size = HDR_SIZE + data_bytes
                    offset += aligned_up(raw_size, SECTOR)
                    # ---- end vectorized block ----

    if not rows:
        return pd.DataFrame(columns=[
            "kit_code","file_name","frame_id","ts_unix",
            "sum_band","sum_all","n_band","n_all","sum_mag_band","sum_log_mag_band"
        ])

    return pd.DataFrame.from_records(rows, columns=[
        "kit_code","file_name","frame_id","ts_unix",
        "sum_band","sum_all","n_band","n_all","sum_mag_band","sum_log_mag_band"
    ])

# =================== Feature construction ===================
def to_frame_features(ff):
    if ff.empty:
        return ff

    ff = ff.copy()
    ff["n_all"]  = ff["n_all"].clip(lower=1)
    ff["n_band"] = ff["n_band"].clip(lower=1)

    bandRMS = np.sqrt(ff["sum_band"] / ff["n_band"])

    sum_noise = np.maximum(ff["sum_all"] - ff["sum_band"], 0.0)
    n_noise   = (ff["n_all"] - ff["n_band"]).clip(lower=1)
    noiseRMS  = np.sqrt(sum_noise / n_noise)
    noiseRMS  = np.maximum(noiseRMS, NOISE_RMS_FLOOR)

    am_mag = (ff["sum_mag_band"] / ff["n_band"]).astype("float64")
    gm_mag = np.exp(ff["sum_log_mag_band"] / ff["n_band"])
    sfm    = (gm_mag / (am_mag + EPS)).astype("float64")
    sfm    = np.clip(sfm, 0, np.inf)

    snr_lin = (bandRMS / noiseRMS) ** 2
    snr_lin = np.clip(snr_lin, 0, SNR_CAP)

    out = ff[["kit_code","file_name","frame_id","ts_unix"]].copy()
    out["bandRMS"]  = bandRMS.astype("float32")
    out["noiseRMS"] = noiseRMS.astype("float32")
    out["sfm"]      = sfm.astype("float32")
    out["snr_lin"]  = snr_lin.astype("float32")
    return out

def estimate_frame_period_seconds(df: pd.DataFrame) -> float:
    """Estimate average frame period (in seconds) from ts_unix differences."""
    if len(df) < 2:
        return np.nan
    diffs = df["ts_unix"].diff().dropna()
    return float(diffs.mean())

# =================== Voice detection & aggregation ===================
def stateful_detect_one_kit(g):
    g = g.sort_values("ts_unix").copy()
    if g.empty:
        return pd.DataFrame(columns=[
            "ts_unix","voice","voiceIntensityDB","voice_score",
            "snr_lin","sfm","noiseRMS","bandRMS"
        ])

    init = g["bandRMS"].head(20).median() if len(g) >= 5 else float(g["bandRMS"].iloc[0])
    baseline = float(max(init, EPS))

    n = len(g)
    voice = np.zeros(n, np.int8)
    inten = np.zeros(n, np.float32)
    score = np.zeros(n, np.float32)

    brms = g["bandRMS"].to_numpy(np.float32, copy=False)
    sfm  = np.nan_to_num(g["sfm"].to_numpy(np.float32, copy=False), nan=1.0)
    snr  = np.nan_to_num(g["snr_lin"].to_numpy(np.float32, copy=False), nan=0.0)

    confirm = 0
    for i in range(n):
        rise_db = max(20.0 * math.log10((float(brms[i]) + EPS) / (baseline + EPS)), 0.0)
        cand = (snr[i] >= SNR_MIN_LINEAR) and (sfm[i] <= SFM_MAX_FOR_VOICE) and (rise_db >= RISE_DB_OVER_BASE)
        confirm = confirm + 1 if cand else 0
        v = 1 if confirm >= CONFIRM_FRAMES else 0
        voice[i] = v
        inten[i] = rise_db if v == 1 else 0.0

        rise_norm = min(max(rise_db/12.0, 0.0), 1.0)
        snr_norm  = min(max((snr[i]-1.0)/4.0, 0.0), 1.0)
        harm_norm = min(max((1.0 - sfm[i])/1.0, 0.0), 1.0)
        score[i]  = float(W_RISE*rise_norm + W_SNR*snr_norm + W_HARM*harm_norm)

        if v == 0:
            baseline = (1.0-BASELINE_ALPHA)*baseline + BASELINE_ALPHA*max(float(brms[i]), EPS)

    out = g[["ts_unix","snr_lin","sfm","noiseRMS","bandRMS"]].copy()
    out["voice"] = voice
    out["voiceIntensityDB"] = inten
    out["voice_score"] = score
    return out

def per_kit_worker(args):
    kit, g, start_ep, end_ep, tz_name = args
    frame_period_s = estimate_frame_period_seconds(g)

    det = stateful_detect_one_kit(g)
    det["kit_code"] = kit
    det["ts_min_utc"] = pd.to_datetime((det["ts_unix"] // 60) * 60, unit="s", utc=True)

    agg = (det.groupby(["kit_code","ts_min_utc"], as_index=False)
           .agg(voice_rate=("voice","mean"),
                intensity_mean=("voiceIntensityDB","mean"),
                voice_score_mean=("voice_score","mean"),
                snr_mean=("snr_lin","mean"),
                sfm_mean=("sfm","mean"),
                noiseRMS_mean=("noiseRMS","mean"),
                bandRMS_mean=("bandRMS","mean"),
                frames=("voice","size"),
                voice_frames=("voice","sum")))

    # Clamp coverage to 60 s
    agg["frame_period_s"] = frame_period_s
    agg["coverage_s"]     = np.minimum(agg["frames"] * frame_period_s, 60.0)
    agg["coverage_rate"]  = (agg["coverage_s"] / 60.0).astype("float32")
    agg["voice_seconds"]  = np.minimum(agg["voice_frames"] * frame_period_s, agg["coverage_s"])
    agg["voice_rate_time"] = np.where(
        agg["coverage_s"] > 0,
        agg["voice_seconds"] / agg["coverage_s"],
        0.0
    ).astype("float32")

    # Minute grid: [start, end) to match frame filter
    t_start = int((start_ep // 60) * 60)
    t_end   = int(((end_ep + 59) // 60) * 60)
    full_idx = pd.date_range(pd.to_datetime(t_start, unit="s", utc=True),
                             pd.to_datetime(t_end,   unit="s", utc=True),
                             freq="1min", inclusive="left")
    grid = (pd.DataFrame({"ts_min_utc": full_idx})
              .assign(kit_code=kit))

    agg = grid.merge(agg, on=["kit_code","ts_min_utc"], how="left")

    for col in ["frames","voice_frames"]:
        agg[col] = agg[col].fillna(0).astype("int32")
    for col in ["coverage_s","coverage_rate","voice_seconds","voice_rate","voice_rate_time"]:
        agg[col] = agg[col].fillna(0.0).astype("float32")

    agg["ts_min_local"] = agg["ts_min_utc"].dt.tz_convert(tz_name)
    return agg

# =================== Main ===================
def main():
    t0 = time.time()
    start_ep, end_ep, tz_name = load_window(YAML_PATH)
    Path(OUT_PARQ).parent.mkdir(parents=True, exist_ok=True)

    ff_raw = stream_frames_to_summaries(INPUT_DIRS, KIT_CODE, start_ep, end_ep)
    if ff_raw.empty:
        cols = ["kit_code","ts_min_utc","ts_min_local","voice_rate","voice_rate_time",
                "intensity_mean","voice_score_mean","snr_mean","sfm_mean",
                "noiseRMS_mean","bandRMS_mean","frames","voice_frames",
                "frame_period_s","coverage_s","coverage_rate","voice_seconds"]
        pd.DataFrame(columns=cols).to_parquet(OUT_PARQ, index=False)
        print(f"[DONE] No frames in window; wrote empty {OUT_PARQ}")
        return

    ff = to_frame_features(ff_raw)
    del ff_raw

    kits = list(ff["kit_code"].unique())
    tasks = []
    for k in kits:
        g = ff.loc[ff["kit_code"] == k, ["ts_unix","bandRMS","noiseRMS","sfm","snr_lin"]].copy()
        tasks.append((k, g, start_ep, end_ep, tz_name))

    print(f"[INFO] Kits: {len(kits)} | Frames total: {len(ff):,}")

    if PARALLEL and len(kits) > 1:
        with Pool(processes=N_WORKERS) as pool:
            parts = pool.map(per_kit_worker, tasks)
        agg = pd.concat(parts, ignore_index=True)
    else:
        agg = pd.concat([per_kit_worker(t) for t in tasks], ignore_index=True)

    try:
        agg.to_parquet(OUT_PARQ, index=False, engine="pyarrow")
    except Exception:
        agg.to_parquet(OUT_PARQ, index=False)

    dt = time.time() - t0
    print(f"[DONE] Saved {OUT_PARQ}  rows={len(agg):,} kits={agg['kit_code'].nunique()}  in {dt:.1f}s")

if __name__ == "__main__":
    main()
