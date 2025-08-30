#!/usr/bin/env python3
# analyzer_md.py — Lean analyzer with clear Markdown conclusions
# Improvements vs previous:
# - Exact one-sided p-values from t-stat (no 2-sided halving); non-integer df = Neff-2
# - FDR (BH) across the *entire* family of tested lags (and noise vars if enabled) per endpoint & scope
# - Reverse-direction (negative-lag) sanity check (reported, not included in FDR family)
# - Optional Spearman rho cross-check (reported in per-lag CSVs; not used for decisions)
# - Effect size r^2 in tables; cleaner Markdown with diagnostics
# - Guard-rails for near-constant data; tunable occupancy proxy via YAML
# - NEW: Presence-controlled residual scope (within OCCUPIED) to isolate speech-linked effects
#
# Inputs:
#   data/processed/airq_1min.parquet
#   data/processed/noise_voice_1min.parquet
# Optional:
#   time_window_unified.yaml  (timezone/start_utc/end_utc and occ_proxy params)
#
# Outputs per pair under reports_clean/<PAIR>/:
#   - headline_results.csv
#   - lag_scans_<scope>_<air>__<noise>.csv            (forward lags)
#   - lag_scans_reverse_<scope>_<air>__<noise>.csv    (negative-lag check)
#   - summary.md
#   - diagnostics.json

from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
import warnings, sys, math, json

warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import yaml
except Exception:
    yaml = None

# ---------------------- Configuration ----------------------
AIRQ_PARQ  = Path("data/processed/airq_1min.parquet")
NOISE_PARQ = Path("data/processed/noise_voice_1min.parquet")
OUTROOT    = Path("reports_clean")
TZ_DEFAULT = "Europe/Madrid"

# Air variables and their hypothesis direction
# 'greater' = expect increase; 'less' = expect decrease; 'two-sided' = no fixed direction
AIR_VARS_CORE = {
    "CO2": "greater",
    "dCO2_mean3": "greater",   # 3-min rolling mean of minute-to-minute CO2 change
    "PM25": "greater",
    "PM10": "greater",
    "TEMP": "two-sided",
    "HUM": "two-sided",
}

# Noise variables
PRIMARY_NOISE        = "voice_rate_time"                # main speech proxy
NOISE_VARS_PRIMARY   = [PRIMARY_NOISE]
NOISE_VARS_ROBUST    = ["intensity_mean", "snr_mean"]   # optional
PRIMARY_ONLY         = True   # True = only PRIMARY_NOISE in headlines/scan files

# Lag ranges (minutes of Noise leading Air)
LAGS_FOR_LEVELS   = list(range(0, 11))   # e.g., CO2 vs voice_rate_time
LAGS_FOR_DERIVED  = list(range(0, 21))   # e.g., dCO2_mean3 vs voice_rate_time
# Reverse-direction (Air leading Noise): NOT included in FDR family; reported for sanity check
LAGS_NEG          = list(range(-10, 0))

# Data-quality filters
COVERAGE_MIN = 0.50  # keep minutes with at least 50% noise coverage
MIN_SAMPLES  = 40    # minimum overlapping samples after alignment and trimming
TRIM_Q       = 0.01  # 1% trimming on each tail for robustness
NEAR_CONST_EPS = 1e-12

# Thresholds
ALPHA  = 0.05                         # decision level
CONF_Z = 1.959963984540054            # 95% two-sided

# Presence-control defaults (can be made YAML-configurable later if desired)
PRES_HALFLIFE_MIN = 30.0  # minutes for low-pass CO2 baseline

# ---------------------- Utilities ----------------------

def read_yaml(p: Path) -> dict:
    if p.exists() and yaml:
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def fix_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.replace("₂", "2") for c in df.columns]  # just in case
    if "kit_code" in df.columns:
        df["kit_code"] = df["kit_code"].astype(str).str.strip().str.upper()
    if "ts_min_utc" in df.columns:
        df["ts_min_utc"] = pd.to_datetime(df["ts_min_utc"], errors="coerce", utc=True)
    return df

def within_window(df: pd.DataFrame, start_utc: str|None, end_utc: str|None) -> pd.DataFrame:
    if start_utc:
        df = df[df["ts_min_utc"] >= pd.Timestamp(start_utc, tz="UTC")]
    if end_utc:
        df = df[df["ts_min_utc"] < pd.Timestamp(end_utc, tz="UTC")]
    return df

def join_minutes(air: pd.DataFrame, noi: pd.DataFrame, air_kit: str, noise_kit: str) -> pd.DataFrame:
    keep_air = ["kit_code", "ts_min_utc", "CO2", "PM25", "PM10", "TEMP", "HUM", "PRES", "LLUM"]
    keep_noi = ["kit_code", "ts_min_utc", "voice_rate", "voice_rate_time", "intensity_mean",
                "voice_score_mean", "snr_mean", "sfm_mean", "frames", "coverage_rate"]
    A = air[air["kit_code"] == air_kit]
    N = noi[noi["kit_code"] == noise_kit]
    A = A[[c for c in keep_air if c in A.columns]].copy()
    N = N[[c for c in keep_noi if c in N.columns]].copy()
    df = pd.merge(A, N, on="ts_min_utc", how="inner", suffixes=("_air", "_noi"))
    df["pair_tag"] = f"{air_kit}_{noise_kit}"
    return df.sort_values("ts_min_utc")

def derive_air_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy().sort_values("ts_min_utc")
    d["dCO2"] = d["CO2"].diff()
    d["dCO2_mean3"] = d["dCO2"].rolling(3, min_periods=2).mean()
    return d

def occ_proxy(df: pd.DataFrame, base_quantile: float = 0.10, base_add: float = 50.0, dco2_thresh: float = 1.5) -> pd.Series:
    # CO2-based occupancy proxy: above low baseline OR gently rising
    co2 = df["CO2"]
    base = float(np.nanpercentile(co2, base_quantile*100.0) + base_add)
    rising = df["dCO2_mean3"].fillna(0) > dco2_thresh
    return ((co2 > base) | rising).astype(int)

def filter_quality(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if "coverage_rate" in d.columns:
        d = d[d["coverage_rate"] >= COVERAGE_MIN]
    if "frames" in d.columns:
        d = d[d["frames"] >= 1]
    return d

def trim_xy(x: np.ndarray, y: np.ndarray, q: float = TRIM_Q):
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 10:
        return x, y
    xlo, xhi = np.quantile(x, q), np.quantile(x, 1 - q)
    ylo, yhi = np.quantile(y, q), np.quantile(y, 1 - q)
    m2 = (x >= xlo) & (x <= xhi) & (y >= ylo) & (y <= yhi)
    return x[m2], y[m2]

def lag1_autocorr(v: np.ndarray) -> float:
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if len(v) < 3:
        return 0.0
    return float(pd.Series(v).autocorr(lag=1) or 0.0)

def corr_with_adj(x: np.ndarray, y: np.ndarray):
    """
    Pearson r with autocorrelation-adjusted p via effective N.
    Returns: r, p2_raw, p2_adj, Neff, r1x, r1y, tval, df
    """
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    N = len(x)
    if N < 3:
        return (np.nan, np.nan, np.nan, 0.0, 0.0, 0.0, np.nan, np.nan)
    # near-constant guard
    if np.var(x) < NEAR_CONST_EPS or np.var(y) < NEAR_CONST_EPS:
        return (np.nan, np.nan, np.nan, 0.0, 0.0, 0.0, np.nan, np.nan)
    r, p2 = stats.pearsonr(x, y)
    r1x = lag1_autocorr(x); r1y = lag1_autocorr(y)
    denom = (1.0 + r1x * r1y)
    Neff = N if denom <= 0 else N * (1.0 - r1x * r1y) / denom
    Neff = float(np.clip(Neff, 3.0, N))
    df = max(1.0, Neff - 2.0)  # allow non-integer df
    t = r * math.sqrt(df) / math.sqrt(max(1e-12, 1.0 - r * r))
    p2_adj = 2.0 * stats.t.sf(abs(t), df)
    return float(r), float(p2), float(p2_adj), Neff, float(r1x), float(r1y), float(t), float(df)

def spearman_with_adj(x: np.ndarray, y: np.ndarray, Neff: float):
    """
    Spearman rho cross-check. Not used for decisions; reported only.
    Returns rho and a Neff-based two-sided p_approx.
    """
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 3 or np.var(x) < NEAR_CONST_EPS or np.var(y) < NEAR_CONST_EPS:
        return (np.nan, np.nan)
    rho, _p = stats.spearmanr(x, y)
    if not np.isfinite(rho) or Neff <= 3:
        return (float(rho) if np.isfinite(rho) else np.nan, np.nan)
    df = max(1.0, Neff - 2.0)
    t = rho * math.sqrt(df) / math.sqrt(max(1e-12, 1.0 - rho * rho))
    p2_adj = 2.0 * stats.t.sf(abs(t), df)
    return float(rho), float(p2_adj)

def p_from_alt(t: float, df: float, alt: str) -> float:
    if not np.isfinite(t) or df <= 0:
        return np.nan
    if alt == "two-sided":
        return 2.0 * stats.t.sf(abs(t), df)
    if alt == "greater":   # H1: r > 0
        return stats.t.sf(t, df)
    if alt == "less":      # H1: r < 0
        return stats.t.cdf(t, df)
    return 2.0 * stats.t.sf(abs(t), df)

def fisher_z_ci(r: float, Neff: float, conf_z: float = CONF_Z):
    if not np.isfinite(r) or Neff <= 3:
        return (np.nan, np.nan)
    z = np.arctanh(np.clip(r, -0.999999, 0.999999))
    se = 1.0 / np.sqrt(Neff - 3.0)
    lo = np.tanh(z - conf_z * se)
    hi = np.tanh(z + conf_z * se)
    return float(lo), float(hi)

def bh_fdr(pvals: list[float]) -> list[float]:
    p = np.array([pv if np.isfinite(pv) else 1.0 for pv in pvals], float)
    n = len(p)
    order = np.argsort(p)
    ranks = np.empty(n, int); ranks[order] = np.arange(1, n+1)
    q = p * n / ranks
    q_sorted = np.minimum.accumulate(q[order][::-1])[::-1]
    q_adj = np.empty_like(p); q_adj[order] = np.clip(q_sorted, 0, 1)
    return q_adj.tolist()

def tail_digits(s: str) -> str:
    digits = "".join([c for c in s if c.isdigit()])
    return digits[-3:] if digits else s

def fmt_sig(x: float, sig: int = 3) -> str:
    if not np.isfinite(x):
        return "NA"
    return f"{x:.{sig}g}"

# ---------- NEW: Presence-control helpers ----------

def lowpass_co2(co2: pd.Series, ts_utc: pd.Series, halflife_min: float = PRES_HALFLIFE_MIN) -> pd.Series:
    """
    Slow baseline CO2 (silent presence + ventilation) via exponential moving average.
    Uses time-aware EWM so it works with irregular minute spacing too.
    """
    hl = float(halflife_min) if np.isfinite(halflife_min) and halflife_min > 0 else 30.0
    return co2.ewm(
        halflife=pd.Timedelta(minutes=hl),
        times=ts_utc,
        adjust=True,          # <-- key change
        min_periods=3
    ).mean()



def cyclic_time_features(ts_utc: pd.Series, tz_local: str) -> pd.DataFrame:
    """Hour-of-day sine/cosine in local time (captures daily rhythm without overfitting)."""
    local = ts_utc.dt.tz_convert(tz_local)
    hod = local.dt.hour + local.dt.minute/60.0
    ang = 2*np.pi*hod/24.0
    return pd.DataFrame({"sin_hod": np.sin(ang), "cos_hod": np.cos(ang)})

def residualize(y: pd.Series, X: pd.DataFrame) -> pd.Series:
    """OLS residuals: y - X @ beta (adds intercept). Returns y-sized Series with NaNs where needed."""
    X_ = X.copy()
    X_["intercept"] = 1.0
    m = y.notna()
    for c in X_.columns:
        m &= X_[c].notna()
    resid = pd.Series(index=y.index, dtype=float)
    if m.sum() < 10:
        return resid  # all NaN -> safely dropped later
    yv = y[m].values
    Xv = X_.loc[m].values
    beta, *_ = np.linalg.lstsq(Xv, yv, rcond=None)
    resid.loc[m] = yv - (Xv @ beta)
    return resid

# ---------------------- Lag scanner ----------------------

def scan_lags(df: pd.DataFrame, air_col: str, noise_col: str, lags: list[int], alt: str):
    """
    Scan a list of lags. Returns list of row dicts. (No FDR here.)
    Each row has: lag_min, N, Neff, r, p_adj(one-sided per alt), r1x, r1y, t, df,
                  spearman_rho, spearman_p_adj
    """
    rows = []
    xs_full = df[air_col].values
    ys_full = df[noise_col].values
    for L in lags:
        ys = pd.Series(ys_full).shift(L).values  # Noise leads Air by +L if L>0; Air leads Noise if L<0
        x, y = trim_xy(xs_full, ys_full if L == 0 else ys)
        if len(x) < MIN_SAMPLES:
            continue
        r, _p2raw, p2a, Neff, r1x, r1y, tval, dfree = corr_with_adj(x, y)
        if not np.isfinite(r):
            continue
        p_adj = p_from_alt(tval, dfree, alt)
        rho, sp_p = spearman_with_adj(x, y, Neff)
        rows.append({
            "lag_min": int(L), "N": int(len(x)), "Neff": float(Neff),
            "r": float(r), "p_adj": float(p_adj), "t": float(tval), "df": float(dfree),
            "r1x": float(r1x), "r1y": float(r1y),
            "spearman_rho": float(rho) if np.isfinite(rho) else np.nan,
            "spearman_p_adj": float(sp_p) if np.isfinite(sp_p) else np.nan
        })
    return rows

# ---------------------- Main Pair Runner ----------------------

def run_pair(air: pd.DataFrame, noise: pd.DataFrame, air_kit: str, noise_kit: str,
             tz_local: str, start_utc: str|None, end_utc: str|None,
             occ_cfg: dict):
    outdir = OUTROOT / f"{air_kit}_{noise_kit}"
    outdir.mkdir(parents=True, exist_ok=True)

    df = join_minutes(air, noise, air_kit, noise_kit)
    if df.empty:
        print(f"[{air_kit}_{noise_kit}] No overlapping minutes.")
        return

    df = within_window(df, start_utc, end_utc)   # hard gate
    if df.empty:
        print(f"[{air_kit}_{noise_kit}] No data within requested window.")
        return

    df = derive_air_features(df)
    df = filter_quality(df)

    # Occupancy proxy params (tunable via YAML)
    base_q = float(occ_cfg.get("base_quantile", 0.10))
    base_add = float(occ_cfg.get("base_add", 50.0))
    dco2_thr = float(occ_cfg.get("dco2_thresh", 1.5))
    df["occ_proxy"] = occ_proxy(df, base_quantile=base_q, base_add=base_add, dco2_thresh=dco2_thr)

    # ---------- NEW: presence & schedule controls (computed once) ----------
    df["CO2_lp"] = lowpass_co2(df["CO2"], df["ts_min_utc"], halflife_min=PRES_HALFLIFE_MIN)
    cyc = cyclic_time_features(df["ts_min_utc"], tz_local)
    df["sin_hod"] = cyc["sin_hod"]; df["cos_hod"] = cyc["cos_hod"]
    co2lp_med = float(np.nanmedian(df["CO2_lp"]))
    co2lp_std = float(np.nanstd(df["CO2_lp"]) + 1e-9)
    df["occ_level"] = (df["CO2_lp"] - co2lp_med) / co2lp_std  # normalized slow presence level

    # Which noise variables to consider
    noise_vars = [v for v in NOISE_VARS_PRIMARY if v in df.columns]
    if not PRIMARY_ONLY:
        noise_vars += [v for v in NOISE_VARS_ROBUST if v in df.columns]

    if not noise_vars:
        print(f"[{air_kit}_{noise_kit}] No noise variables available after join.")
        return

    # Coverage summary for context
    n_all = len(df)
    n_occ = int(df["occ_proxy"].sum())
    cov_mean_all = float(df.get("coverage_rate", pd.Series([np.nan]*n_all)).mean())
    cov_mean_occ = float(df[df["occ_proxy"]==1].get("coverage_rate", pd.Series([np.nan]*max(n_occ,1))).mean()) if n_occ>0 else np.nan

    results_rows = []
    neg_check = {"ALL": {}, "OCCUPIED": {}, "PRESENCE_CTRL": {}}
    scans_written = []

    def scope_block(tag: str, dfin: pd.DataFrame):
        if dfin.empty:
            return
        for air_var, alt in AIR_VARS_CORE.items():
            lags = LAGS_FOR_DERIVED if air_var in ("dCO2_mean3",) else LAGS_FOR_LEVELS
            # Collect ALL forward rows for this endpoint across noise vars → one BH family
            family_rows = []        # forward rows for FDR
            family_indices = []     # (noise_var, idx_within_rows) to map back q_BH
            forward_rows_by_noise = {}
            reverse_rows_by_noise = {}

            # ---- scan forward lags (for FDR) and negative lags (diagnostic only)
            for noise_var in noise_vars:
                ok = dfin[[air_var, noise_var]].dropna()
                if len(ok) < MIN_SAMPLES:
                    continue
                rows_fwd = scan_lags(dfin, air_var, noise_var, lags, alt)
                if rows_fwd:
                    # annotate origin (noise var) for later reporting
                    for r in rows_fwd:
                        r["noise_var"] = noise_var
                    forward_rows_by_noise[noise_var] = rows_fwd
                    for i, row in enumerate(rows_fwd):
                        family_rows.append(row)
                        family_indices.append((noise_var, i))

                # Reverse-direction check (do NOT include in BH family)
                rows_rev = scan_lags(dfin, air_var, noise_var, LAGS_NEG, "two-sided")
                if rows_rev:
                    reverse_rows_by_noise[noise_var] = rows_rev

            if not family_rows:
                continue

            # ---- Apply a single BH-FDR across the whole family (all fwd lags × noise vars)
            pvals = [row["p_adj"] for row in family_rows]
            qvals = bh_fdr(pvals)
            for row, q in zip(family_rows, qvals):
                row["q_BH"] = float(q)

            # propagate q_BH back to the per-noise lists & write CSVs
            for (noise_var, i), q in zip(family_indices, qvals):
                forward_rows_by_noise[noise_var][i]["q_BH"] = float(q)

            # write forward and reverse scans
            for noise_var, rows_fwd in forward_rows_by_noise.items():
                pd.DataFrame(rows_fwd).to_csv(outdir / f"lag_scans_{tag}_{air_var}__{noise_var}.csv", index=False)
                scans_written.append(f"lag_scans_{tag}_{air_var}__{noise_var}.csv")
            for noise_var, rows_rev in reverse_rows_by_noise.items():
                pd.DataFrame(rows_rev).to_csv(outdir / f"lag_scans_reverse_{tag}_{air_var}__{noise_var}.csv", index=False)

            # ---- Pick best forward row by min q_BH (then p_adj)
            best = min(family_rows, key=lambda r: (r.get("q_BH", 1.0), r["p_adj"]))

            lo, hi = fisher_z_ci(best["r"], best["Neff"], CONF_Z)

            # One-sided sign rule for one-sided endpoints
            def _sign_ok(r, alt):
                if alt == "greater": return r > 0
                if alt == "less":    return r < 0
                return True

            decision = "Reject H0" if (best["q_BH"] <= ALPHA and _sign_ok(best["r"], alt)) else "Fail to reject H0"

            # Reverse diagnostic summary: max |r| and its lag/noise_var
            max_abs_r = None; max_abs_row = None; max_noise = None
            for nvar, rows_rev in reverse_rows_by_noise.items():
                for rr in rows_rev:
                    if (max_abs_r is None) or (abs(rr["r"]) > abs(max_abs_r)):
                        max_abs_r = rr["r"]; max_abs_row = rr; max_noise = nvar
            if max_abs_row:
                neg_check[tag][air_var] = {"max_abs_r": float(max_abs_r),
                                           "lag_min": int(max_abs_row["lag_min"]),
                                           "noise_var": max_noise}
            else:
                neg_check[tag][air_var] = {"max_abs_r": np.nan, "lag_min": None, "noise_var": None}

            results_rows.append({
                "pair": f"{air_kit}_{noise_kit}", "scope": tag,
                "air_var": air_var, "alt": alt, "noise_var": best.get("noise_var",""),
                "best_lag_min": int(best["lag_min"]), "N": int(best["N"]), "Neff": round(best["Neff"], 1),
                "pearson_r": round(best["r"], 3),
                "r2": round(best["r"]**2, 3),
                "r_CI95_lo": round(lo, 3), "r_CI95_hi": round(hi, 3),
                "p_adj": float(best["p_adj"]), "q_BH": float(best["q_BH"]),
                "decision": decision,
                "rev_max_abs_r": float(neg_check[tag][air_var]["max_abs_r"]) if np.isfinite(neg_check[tag][air_var]["max_abs_r"]) else np.nan,
                "rev_max_lag": int(neg_check[tag][air_var]["lag_min"]) if neg_check[tag][air_var]["lag_min"] is not None else "",
                "rev_noise_var": neg_check[tag][air_var]["noise_var"] or ""
            })

    # ---------- Three scopes: ALL, OCCUPIED, and (NEW) PRESENCE_CTRL ----------
    scope_block("ALL", df)
    scope_block("OCCUPIED", df[df["occ_proxy"] == 1])

    # Presence-controlled residuals: within OCCUPIED, remove slow presence + daily rhythm from both Air and Voice
    d_occ = df[df["occ_proxy"] == 1].copy()
    if not d_occ.empty:
        X_ctrl = d_occ[["occ_level", "sin_hod", "cos_hod"]].copy()
        d_res = d_occ.copy()
        # Residualize Air endpoints
        for air_var in AIR_VARS_CORE.keys():
            if air_var in d_res.columns:
                d_res[air_var] = residualize(d_occ[air_var], X_ctrl)
        # Residualize Noise variables used in this run
        for noise_var in noise_vars:
            if noise_var in d_res.columns:
                d_res[noise_var] = residualize(d_occ[noise_var], X_ctrl)
        scope_block("PRESENCE_CTRL", d_res)

    if not results_rows:
        print(f"[{air_kit}_{noise_kit}] No valid results after filters.")
        return

    res = pd.DataFrame(results_rows).sort_values(["scope", "air_var", "p_adj"])
    res.to_csv(outdir / "headline_results.csv", index=False)

    # -------- Markdown summary (clean & compact) --------
    def decision_symbol(dec: str) -> str:
        return "✓" if dec.startswith("Reject") else "✗"

    def best_by_endpoint(scope: str, air_var: str) -> dict|None:
        sub = res[(res["scope"] == scope) & (res["air_var"] == air_var)]
        if sub.empty:
            return None
        sub = sub.sort_values(["q_BH", "p_adj"])
        return sub.iloc[0].to_dict()

    def bullets_for_scope(scope: str):
        lines = []
        for air_var, alt in AIR_VARS_CORE.items():
            row = best_by_endpoint(scope, air_var)
            if not row:
                continue
            ci = f"[{row['r_CI95_lo']:+.3f}, {row['r_CI95_hi']:+.3f}]"
            lines.append(
                f"• **{air_var}:** {decision_symbol(row['decision'])} best lag **+{int(row['best_lag_min'])} min**, "
                f"r={row['pearson_r']:+.3f} (95% CI {ci}), r²={row['r2']:.3f}, q={fmt_sig(row['q_BH'])}, "
                f"N_eff/N={row['Neff']:.0f}/{row['N']}"
            )
        return lines

    def alt_statements():
        items = []
        for air_var, alt in AIR_VARS_CORE.items():
            if alt == "greater":
                H0, H1 = "corr ≤ 0", "corr > 0"
            elif alt == "less":
                H0, H1 = "corr ≥ 0", "corr < 0"
            else:
                H0, H1 = "corr = 0", "corr ≠ 0"
            items.append(f"- **{air_var}** — Alt: **{alt}**  •  H₀: {H0}  •  H₁: {H1}")
        return items

    def neg_lines(scope: str):
        out = []
        for air_var in AIR_VARS_CORE.keys():
            d = res[(res["scope"] == scope) & (res["air_var"] == air_var)]
            if d.empty:
                continue
            row = d.iloc[0]
            maxr = row.get("rev_max_abs_r", np.nan)
            lagm = row.get("rev_max_lag", "")
            nvar = row.get("rev_noise_var", "")
            if np.isfinite(maxr):
                out.append(f"• **{air_var}:** reverse check max |r|={abs(maxr):.3f} at lag {lagm} min (noise={nvar})")
            else:
                out.append(f"• **{air_var}:** reverse check: no valid negative-lag data")
        return out

    scopes_present = [s for s in ["ALL", "OCCUPIED", "PRESENCE_CTRL"] if (res["scope"] == s).any()]

    md = []
    md += [f"# Analysis Summary — {air_kit} × {noise_kit}",
           "",
           f"_Window_: {start_utc or 'ALL'} → {end_utc or 'ALL'}  •  _Timezone_: {tz_local}",
           f"_Minutes analysed (after quality filter)_: ALL={n_all}, OCCUPIED={n_occ}  •  Mean noise coverage: ALL={cov_mean_all:.2f}, OCC={cov_mean_occ:.2f}",
           "",
           "## Executive summary",
           f"- **Family-wise control:** BH-FDR across all tested lags{'' if PRIMARY_ONLY else ' and noise variables'} per endpoint at α=0.05.",
           "- **Interpretation rule:** For one-sided endpoints (CO₂, ΔCO₂, PM), the sign must match the alternative.",
           ""]
    if "ALL" in scopes_present:
        md += ["### Key endpoints (ALL minutes)"] + bullets_for_scope("ALL") + [""]
    if "OCCUPIED" in scopes_present:
        md += ["### Key endpoints (OCCUPIED minutes)"] + bullets_for_scope("OCCUPIED") + [""]
    if "PRESENCE_CTRL" in scopes_present:
        md += ["### Presence-controlled (OCCUPIED residuals)",
               "_Slow presence (low-pass CO₂) and daily rhythm removed from both Voice and Air before lag scan._"]
        md += bullets_for_scope("PRESENCE_CTRL") + [""]

    md += ["### Reverse-direction (negative-lag) diagnostics",
           "_Air leading Noise (-10…-1 min); not part of FDR family._",
           "**ALL:**"] + neg_lines("ALL") + ["",
           "**OCCUPIED:**"] + neg_lines("OCCUPIED") + ["",
           "## Hypotheses by endpoint"] + alt_statements() + ["",
           "## Variables",
           f"- **Noise (primary)**: `{PRIMARY_NOISE}`" + ("" if PRIMARY_ONLY else f"; Robustness: {', '.join([v for v in NOISE_VARS_ROBUST if v in noise_vars])}"),
           "- **Air**: `CO2`, `dCO2_mean3` (3-min mean of ΔCO₂), `PM25`, `PM10`, `TEMP`, `HUM`",
           "",
           "## Best-lag details (per scope & endpoint)",
           "_Shows the best-performing Noise variable and lag for each air endpoint._",
           ""]
    for scope in scopes_present:
        sub = res[res["scope"] == scope]
        if sub.empty:
            continue
        md += [f"### {scope}",
               "",
               "| Air | Alt | Noise | Lag+min | r | r² | 95% CI | Neff/N | p_adj | q_BH | Decision |",
               "|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---|"]
        for air_var in AIR_VARS_CORE.keys():
            row = best_by_endpoint(scope, air_var)
            if not row:
                continue
            ci = f"[{row['r_CI95_lo']:+.3f}, {row['r_CI95_hi']:+.3f}]"
            md += [f"| {air_var} | {row['alt']} | {row['noise_var']} | +{int(row['best_lag_min'])} | "
                   f"{row['pearson_r']:+.3f} | {row['r2']:.3f} | {ci} | "
                   f"{row['Neff']:.0f}/{row['N']} | {fmt_sig(row['p_adj'])} | {fmt_sig(row['q_BH'])} | {row['decision']} |"]
        md += [""]

    md += ["## Methods (short)",
           "- **Pearson r** on aligned minute pairs after shifting Noise forward by lag L.",
           "- **Autocorrelation-aware testing:** estimate lag-1 autocorr for each series, derive an **effective N** (N_eff), compute **t** and **p** with df = N_eff − 2 (real-valued).",
           "- **One-sided tests** implemented directly from t and df (no halving of two-sided p).",
           "- **FDR (BH)** across all forward lags" + ("" if PRIMARY_ONLY else " and noise variables") + " per endpoint/scope → **q**; we pick the minimum-q lag (ties by p).",
           "- **95% CI** for r via **Fisher z** using N_eff; we also report **r²** as effect size.",
           "- **Reverse-direction** (negative lags) scanned and reported for plausibility; excluded from FDR.",
           "- **Spearman ρ** reported in per-lag CSVs as a robustness check; not used in decisions.",
           "- **Quality**: minutes require `coverage_rate ≥ 0.50` and ≥1 frame; window gating occurs pre-analysis.",
           f"- **Occupancy proxy** parameters: base_quantile={base_q}, base_add={base_add}, dCO2_thresh={dco2_thr}.",
           "- **Presence-controlled scope:** inside OCCUPIED minutes, remove slow presence (low-pass CO₂, halflife 30 min) and daily rhythm (hour-of-day sine/cosine) from both Voice and Air, then re-run the same lag scan.",
           ""]
    (outdir / "summary.md").write_text("\n".join(md), encoding="utf-8")

    # Diagnostics JSON (lightweight)
    diag = {
        "pair": f"{air_kit}_{noise_kit}",
        "window": {"start_utc": start_utc, "end_utc": end_utc, "timezone": tz_local},
        "minutes_after_quality": {"ALL": n_all, "OCCUPIED": n_occ},
        "mean_coverage": {"ALL": cov_mean_all, "OCCUPIED": cov_mean_occ},
        "neg_checks": neg_check,
        "scans_written": scans_written,
        "presence_ctrl": "PRESENCE_CTRL" in scopes_present,
        "presence_halflife_min": PRES_HALFLIFE_MIN,
    }
    (outdir / "diagnostics.json").write_text(json.dumps(diag, indent=2), encoding="utf-8")

    # Console headline (compact)
    print(f"\n[{air_kit}_{noise_kit}] Executive verdict")
    for scope in scopes_present:
        print(f"  {scope}:")
        for air_var in AIR_VARS_CORE.keys():
            row = res[(res["scope"] == scope) & (res["air_var"] == air_var)]
            if row.empty:
                continue
            row = row.iloc[0]
            print(f"    {air_var}: {row['decision']} • lag +{int(row['best_lag_min'])} • r={row['pearson_r']:+.3f} • q={fmt_sig(row['q_BH'])}")

def run():
    OUTROOT.mkdir(parents=True, exist_ok=True)
    if not AIRQ_PARQ.exists() or not NOISE_PARQ.exists():
        print("ERROR: Expected parquet files not found. Place them under data/processed/.", file=sys.stderr)
        sys.exit(1)
    air = fix_columns(pd.read_parquet(AIRQ_PARQ))
    noise = fix_columns(pd.read_parquet(NOISE_PARQ))

    cfg = read_yaml(Path("time_window_unified.yaml"))
    tz_local = cfg.get("timezone", TZ_DEFAULT)
    start_utc = cfg.get("start_utc")
    end_utc   = cfg.get("end_utc")
    occ_cfg   = cfg.get("occ_proxy", {}) if isinstance(cfg, dict) else {}

    air_kits = sorted(air["kit_code"].unique()) if "kit_code" in air.columns else []
    noise_kits = sorted(noise["kit_code"].unique()) if "kit_code" in noise.columns else []

    # Pairing: match numeric tails (e.g., AIRQ001 with NOISE001).
    pairs = []
    tail = lambda s: tail_digits(s)
    if air_kits and noise_kits:
        for ak in air_kits:
            for nk in noise_kits:
                if tail(ak) == tail(nk) or len(noise_kits) == 1:
                    pairs.append((ak, nk))
    if not pairs and air_kits and noise_kits:
        pairs = [(air_kits[0], noise_kits[0])]

    if not pairs:
        print("No kit pairs found to analyse."); return

    for ak, nk in pairs:
        run_pair(air, noise, ak, nk, tz_local, start_utc, end_utc, occ_cfg)

if __name__ == "__main__":
    run()
