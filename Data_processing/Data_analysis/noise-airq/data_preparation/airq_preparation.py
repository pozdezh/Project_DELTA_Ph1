#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3, pandas as pd, numpy as np, yaml, time
from pathlib import Path

# -------- Paths
DB_PATH      = r"X:\TFG_extra\EXPERIMENT_DATA\database_exp\experiment_1_data.db"
WINDOW_YAML  = r"config\time_window_unified.yaml"   # has window.local/utc_iso/epoch_utc + timezone
WEIGHTS_YAML = r"config\weights.yaml"               # weights for TEMP/HUM only
OUT_PARQ     = r"data\processed\airq_1min.parquet"

pd.set_option("mode.copy_on_write", True)

# -------- Parameters
PARAMS_ALL = ["TEMP","HUM","CO2","PRES","LLUM",
              "PM1","PM25","PM10","UM03","UM05","UM1","UM25","UM5","UM10"]
WEIGHTED   = {"TEMP","HUM"}   # only these get weights

# -------- Load window (also return LOCAL strings)
def load_window(yaml_file):
    with open(yaml_file, "r") as f:
        cfg = yaml.safe_load(f)
    tz = cfg.get("timezone", "Europe/Madrid")
    start_ep = int(cfg["window"]["epoch_utc"]["start"])
    end_ep   = int(cfg["window"]["epoch_utc"]["end"])
    start_local = cfg["window"]["local"]["start"]
    end_local   = cfg["window"]["local"]["end"]
    return start_ep, end_ep, tz, start_local, end_local

# -------- Load weights (uppercased keys)
def load_weights(yaml_file):
    with open(yaml_file, "r") as f:
        data = yaml.safe_load(f)
    W = {}
    for par, mapping in (data.get("weights") or {}).items():
        W[par.upper()] = {str(k).upper(): float(v) for k, v in mapping.items()}
    return W

# -------- DB helpers
def ensure_indexes(conn):
    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_airq_param_time ON airq_raw(id_parameter, created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_airq_kit_time   ON airq_raw(kit_code, created_at)")
    conn.commit()

def fetch_airq_local(conn, start_local_str, end_local_str):
    """
    Pull only the parameters we care about, filtering by LOCAL time strings
    (matches how created_at is stored). We then convert to UTC in pandas.
    """
    params_sql = ",".join([f"'{p}'" for p in PARAMS_ALL])
    q = f"""
    SELECT
      kit_code,
      UPPER(id_sensor)     AS id_sensor,
      UPPER(id_parameter)  AS id_parameter,
      created_at,                          -- keep as TEXT, local time
      CAST(value AS REAL)  AS value
    FROM airq_raw
    WHERE UPPER(id_parameter) IN ({params_sql})
      AND created_at BETWEEN ? AND ?
    """
    t0 = time.time()
    df = pd.read_sql(q, conn, params=(start_local_str, end_local_str))
    kits = df["kit_code"].nunique() if not df.empty else 0
    print(f"[SQL] airq_raw: {len(df):,} rows in {time.time()-t0:.1f}s  kits={kits}")
    return df

# -------- Weighted fusion (TEMP/HUM ONLY) — warning-free
def fuse_weighted(sensor_min: pd.DataFrame, param: str, weight_map: dict) -> pd.DataFrame:
    """
    sensor_min: per-sensor-per-minute means
      cols: kit_code, id_parameter, id_sensor, ts_min_utc, value_mean, samples
    Returns columns: kit_code, ts_min_utc, <param>, <param>_sources, <param>_samples
    """
    g = sensor_min[sensor_min["id_parameter"] == param].copy()
    if g.empty:
        return pd.DataFrame(columns=["kit_code","ts_min_utc",param,
                                     f"{param}_sources",f"{param}_samples"])

    # sensor -> weight; unknowns get 0
    g["w"] = g["id_sensor"].map(lambda s: weight_map.get(str(s).upper(), 0.0)).astype(float)

    # Total samples in minute (all sensors, for QA)
    sam = (g.groupby(["kit_code","ts_min_utc"])["samples"]
             .sum().rename(f"{param}_samples"))

    gpos = g[g["w"] > 0].copy()
    if gpos.empty:
        out = sam.to_frame().reset_index()
        out[param] = np.nan
        out[f"{param}_sources"] = 0
        return out[["kit_code","ts_min_utc",param,f"{param}_sources",f"{param}_samples"]]

    # Weighted numerator and denominator per (kit, minute) — no groupby.apply
    num = (gpos["value_mean"] * gpos["w"]).groupby([gpos["kit_code"], gpos["ts_min_utc"]]).sum()
    den = gpos.groupby(["kit_code","ts_min_utc"])["w"].sum().replace(0, np.nan)
    val = (num / den).rename(param)

    # source count (unique weighted sensors)
    src = gpos.groupby(["kit_code","ts_min_utc"])["id_sensor"].nunique().rename(f"{param}_sources")

    out = pd.concat([val, src, sam], axis=1).reset_index()
    return out[["kit_code","ts_min_utc",param,f"{param}_sources",f"{param}_samples"]]

# -------- Unweighted conservation (ALL NON-WEIGHTED PARAMS)
def fuse_unweighted(sensor_min: pd.DataFrame, params: list[str]) -> pd.DataFrame:
    """
    Simple per-minute mean across sensors (if multiple exist).
    Returns wide frame with one column per parameter.
    """
    if not params:
        return pd.DataFrame(columns=["kit_code","ts_min_utc"])
    g = sensor_min[sensor_min["id_parameter"].isin(params)].copy()
    if g.empty:
        return pd.DataFrame(columns=["kit_code","ts_min_utc"] + params)
    val = (g.groupby(["kit_code","ts_min_utc","id_parameter"])["value_mean"]
             .mean()
             .unstack("id_parameter"))
    val = val.reindex(columns=params)
    return val.reset_index()[["kit_code","ts_min_utc"] + params]

# -------- Main
def main():
    start_ep, end_ep, tz_name, start_local_str, end_local_str = load_window(WINDOW_YAML)
    W = load_weights(WEIGHTS_YAML)   # weights only used for TEMP/HUM
    Path(OUT_PARQ).parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        ensure_indexes(conn)
        df = fetch_airq_local(conn, start_local_str, end_local_str)

    if df.empty:
        cols = (["kit_code","ts_min_utc","ts_min_local"] + PARAMS_ALL +
                ["TEMP_sources","HUM_sources","TEMP_samples","HUM_samples"])
        pd.DataFrame(columns=cols).to_parquet(OUT_PARQ, index=False)
        print(f"[DONE] No data; wrote empty {OUT_PARQ}")
        return

    # Normalize text cols defensively
    df["id_parameter"] = df["id_parameter"].astype(str).str.upper()
    df["id_sensor"]    = df["id_sensor"].astype(str).str.upper()

    # --- Correct time handling: created_at is LOCAL; localize then convert to UTC
    ts_local = pd.to_datetime(df["created_at"], errors="coerce")
    # Localize to provided timezone (DST-aware). Ambiguous → NaT; nonexistent → shift_forward.
    ts_local = ts_local.dt.tz_localize(tz_name, ambiguous="NaT", nonexistent="shift_forward")
    ts_utc   = ts_local.dt.tz_convert("UTC")
    # Drop rows that failed to localize/convert
    ok = ts_utc.notna()
    df = df.loc[ok].copy()
    ts_utc = ts_utc.loc[ok]

    df["ts_unix"]     = (ts_utc.astype("int64") // 1_000_000_000)
    df["ts_min_utc"]  = ts_utc.dt.floor("min")

    # Keep only rows inside the epoch window (paranoid double-clip)
    df = df[(df["ts_unix"] >= start_ep) & (df["ts_unix"] <= end_ep)].copy()
    if df.empty:
        cols = (["kit_code","ts_min_utc","ts_min_local"] + PARAMS_ALL +
                ["TEMP_sources","HUM_sources","TEMP_samples","HUM_samples"])
        pd.DataFrame(columns=cols).to_parquet(OUT_PARQ, index=False)
        print(f"[DONE] No data after window clip; wrote empty {OUT_PARQ}")
        return

    # Per-sensor-per-minute mean & count
    sensor_min = (df.groupby(["kit_code","id_parameter","id_sensor","ts_min_utc"], as_index=False)
                    .agg(value_mean=("value","mean"),
                         samples=("value","size")))

    # Weighted TEMP/HUM
    temp_w = fuse_weighted(sensor_min, "TEMP", W.get("TEMP", {}))
    hum_w  = fuse_weighted(sensor_min, "HUM",  W.get("HUM",  {}))
    fused_th = pd.merge(temp_w, hum_w, on=["kit_code","ts_min_utc"], how="outer", sort=True)

    # Unweighted others (conserved)
    other_params = [p for p in PARAMS_ALL if p not in WEIGHTED]
    others = fuse_unweighted(sensor_min, other_params)

    # Merge all
    out = pd.merge(fused_th, others, on=["kit_code","ts_min_utc"], how="outer", sort=True)

    # -------- Full-window grid per kit (forces start at YAML window start)
    kits = df["kit_code"].dropna().unique()
    t_start = pd.to_datetime((start_ep // 60) * 60, unit="s", utc=True)
    t_end   = pd.to_datetime(((end_ep + 59) // 60) * 60, unit="s", utc=True)

    full_grid = pd.DataFrame({"ts_min_utc": pd.date_range(t_start, t_end, freq="1min")})
    grid = pd.concat([(full_grid.assign(kit_code=kit)) for kit in kits], ignore_index=True)

    out = grid.merge(out, on=["kit_code","ts_min_utc"], how="left")

    # Local time
    out["ts_min_local"] = out["ts_min_utc"].dt.tz_convert(tz_name)

    # Ensure final columns exist & order
    final_cols = ["kit_code","ts_min_utc","ts_min_local"] + PARAMS_ALL + \
                 ["TEMP_sources","HUM_sources","TEMP_samples","HUM_samples"]
    for c in final_cols:
        if c not in out.columns:
            out[c] = np.nan
    out = out[final_cols].sort_values(["kit_code","ts_min_utc"]).reset_index(drop=True)

    # Save (prefer pyarrow; fallback otherwise)
    try:
        out.to_parquet(OUT_PARQ, index=False, engine="pyarrow")
    except Exception:
        out.to_parquet(OUT_PARQ, index=False)

    kits_n = out["kit_code"].nunique(dropna=True)
    print(f"[DONE] Saved {OUT_PARQ}  rows={len(out):,} kits={kits_n}")

if __name__ == "__main__":
    main()
