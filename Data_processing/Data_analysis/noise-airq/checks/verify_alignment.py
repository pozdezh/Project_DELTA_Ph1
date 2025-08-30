# checks/verify_airq_noise_alignment.py
from pathlib import Path
import pandas as pd
import numpy as np

# -------- Paths (edit if needed)
AIRQ_PARQ  = Path("data/processed/airq_1min.parquet")
NOISE_PARQ = Path("data/processed/noise_voice_1min.parquet")
OUT_DIR    = Path("reports/checks")

# Pairs we expect in your setup
PAIRS = [("AIRQ001", "NOISE102"), ("AIRQ002", "NOISE102")]

# Vars to sanity-check downstream feasibility
AIR_VARS   = ["CO2", "PM25", "PM10", "HUM", "TEMP"]
NOISE_VARS = ["voice_rate", "snr_mean"]

# As-of tolerance sweep (in minutes)
TOLERANCES_MIN = [0, 1, 2, 5, 10]

def ensure_dirs():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

def _ensure_minute_utc(s):
    """Ensure tz-aware UTC and floored to minute."""
    ts = pd.to_datetime(s, utc=None, errors="coerce")
    ts = ts.dt.tz_localize("UTC") if getattr(ts.dt, "tz", None) is None else ts.dt.tz_convert("UTC")
    return ts.dt.floor("T")

def load_norm():
    air = pd.read_parquet(AIRQ_PARQ)
    noi = pd.read_parquet(NOISE_PARQ)

    # Normalize colnames (CO₂→CO2) and kit_code casing/spaces
    def fix_cols(df):
        df = df.rename(columns={c: c.replace("₂","2").strip() for c in df.columns})
        df["kit_code"] = df["kit_code"].astype(str).str.strip().str.upper()
        return df

    air = fix_cols(air)
    noi = fix_cols(noi)

    # Normalize ts to minute UTC (tz-aware)
    if "ts_min_utc" not in air.columns:
        raise RuntimeError("AirQ parquet missing ts_min_utc")
    if "ts_min_utc" not in noi.columns:
        raise RuntimeError("Noise parquet missing ts_min_utc")

    air["ts_min_utc"] = _ensure_minute_utc(air["ts_min_utc"])
    noi["ts_min_utc"] = _ensure_minute_utc(noi["ts_min_utc"])

    return air, noi

def summarize(df, name):
    print(f"\n[{name}] rows={len(df):,}  cols={len(df.columns)}")
    print(f"[{name}] kits={sorted(df['kit_code'].dropna().unique())}")
    if len(df):
        print(f"[{name}] span: {df['ts_min_utc'].min()} → {df['ts_min_utc'].max()}")
    # quick dtype heads
    dtypes = df.dtypes.astype(str)
    print(f"[{name}] ts tz-aware?  {str(df['ts_min_utc'].dtype)}")

def minute_intersection(A, N):
    a_set = set(A["ts_min_utc"].unique())
    n_set = set(N["ts_min_utc"].unique())
    return len(a_set & n_set)

def strict_join(A, N):
    return pd.merge(A, N, on="ts_min_utc", how="inner", suffixes=("_air", "_noi"))

def asof_join(A, N, tol_min):
    tol = pd.Timedelta(minutes=tol_min)
    L = A.sort_values("ts_min_utc").rename(columns={"ts_min_utc":"ts"})
    R = N.sort_values("ts_min_utc").rename(columns={"ts_min_utc":"ts"})
    J = pd.merge_asof(L, R, on="ts", direction="nearest", tolerance=tol, suffixes=("_air","_noi"))
    # Retain rows where some noise value exists
    noise_cols = [c for c in R.columns if c not in ("ts","kit_code")]
    if noise_cols:
        J = J.dropna(subset=noise_cols, how="all")
    J = J.rename(columns={"ts":"ts_min_utc"})
    return J

def count_non_null_pairs(df, air_vars, noise_vars, tag):
    rows=[]
    for a in air_vars:
        if a not in df.columns: continue
        for n in noise_vars:
            if n not in df.columns: continue
            sub = df[[a, n]].dropna()
            rows.append({"air_var":a, "noise_var":n, "N_non_null_pairs": len(sub)})
    out = pd.DataFrame(rows).sort_values(["air_var","noise_var"])
    out.to_csv(OUT_DIR / f"non_null_counts_{tag}.csv", index=False)
    return out

def main():
    ensure_dirs()
    air, noi = load_norm()
    summarize(air, "AirQ")
    summarize(noi, "Noise")

    # Optional: filter out noise minutes that have zero coverage if you want "real" data only
    # (voice_rate already fills zeros, but snr_mean stays NaN when no frames)
    noi_real = noi.copy()
    if "coverage_s" in noi_real.columns:
        noi_real = noi_real[noi_real["coverage_s"].fillna(0) > 0]

    # Per-pair checks
    for air_code, noise_code in PAIRS:
        print(f"\n=== CHECK {air_code} ↔ {noise_code} ===")
        A = air[air["kit_code"] == air_code].copy()
        N = noi[noi["kit_code"] == noise_code].copy()
        NR = noi_real[noi_real["kit_code"] == noise_code].copy()

        if A.empty:
            print(f"[WARN] No Air rows for {air_code}")
            continue
        if N.empty:
            print(f"[WARN] No Noise rows for {noise_code}")
            continue

        inter_all = minute_intersection(A, N)
        inter_real = minute_intersection(A, NR) if len(NR) else 0
        print(f"[INFO] Minute intersection (all noise minutes): {inter_all}")
        print(f"[INFO] Minute intersection (noise minutes with frames>0): {inter_real}")

        # Strict time-only join
        # We keep the Air kit_code as the row label.
        A_keep = A[["ts_min_utc","kit_code"] + [c for c in AIR_VARS if c in A.columns]]
        N_keep = N[["ts_min_utc"] + [c for c in NOISE_VARS if c in N.columns]]
        J_strict = strict_join(A_keep, N_keep)
        J_strict = J_strict.rename(columns={"kit_code":"kit_code_air"})
        J_strict.insert(1, "kit_code", J_strict.pop("kit_code_air"))
        print(f"[JOIN strict] rows={len(J_strict):,}")
        if len(J_strict):
            sample_path = OUT_DIR / f"sample_strict_{air_code}_{noise_code}.csv"
            J_strict.head(50).to_csv(sample_path, index=False)
            print(f"[JOIN strict] Wrote sample → {sample_path}")

        # As-of tolerance sweep
        summary = []
        for tol in TOLERANCES_MIN:
            J = asof_join(A_keep, N_keep, tol)
            summary.append({"tolerance_min": tol, "rows": len(J)})
            if tol in (0, 2, 10) and len(J):
                p = OUT_DIR / f"sample_asof_tol{tol}_{air_code}_{noise_code}.csv"
                J.head(50).to_csv(p, index=False)
        df_sum = pd.DataFrame(summary)
        print(df_sum.to_string(index=False))
        df_sum.to_csv(OUT_DIR / f"asof_summary_{air_code}_{noise_code}.csv", index=False)

        # Non-null counts for key pairs (tells us if analysis will have enough rows)
        nn = count_non_null_pairs(J_strict if len(J_strict) else asof_join(A_keep, N_keep, max(TOLERANCES_MIN)),
                                  AIR_VARS, NOISE_VARS, f"{air_code}_{noise_code}")
        if not nn.empty:
            print(f"[NON-NULL] key pairs (first rows):\n{nn.head().to_string(index=False)}")

if __name__ == "__main__":
    main()
