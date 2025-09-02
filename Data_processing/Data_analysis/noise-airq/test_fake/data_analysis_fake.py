#!/usr/bin/env python3
# analyzer_md_csv.py — Lean analyzer (CSV in, Markdown out)
# Same stats/logic as your analyzer:
# - Pearson r; one-sided p from t with df=Neff-2 (Neff from lag-1 AR)
# - BH-FDR across all forward lags per endpoint & scope
# - Reverse (negative-lag) check for sanity (not in FDR family)
# - Presence-controlled scope (within OCCUPIED): residualize Air+Noise by slow CO2 baseline + diurnal cycle
# - Robust trimming, quality gates, r², 95%CI (Fisher-z)
#
# Inputs (default names; can override via CLI):
#   ./airq_1min_fake.csv (or *_strong.csv)
#   ./noise_voice_1min_fake.csv (or *_strong.csv)
# Optional:
#   ./time_window_unified.yaml (timezone/start_utc/end_utc + occ_proxy params)
#
# Output:
#   ./summary.md

from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
import warnings, sys, math, json

warnings.filterwarnings("ignore", category=FutureWarning)

# --- SciPy for stats ---
try:
    from scipy import stats
except Exception as e:
    sys.stderr.write("ERROR: scipy is required (t-dist, pearsonr). Install with `pip install scipy`.\n")
    raise

# --- YAML optional (time window + occ params) ---
try:
    import yaml
except Exception:
    yaml = None

# ---------------------- Configuration ----------------------
# Resolve paths relative to this script's directory
HERE = Path(__file__).resolve().parent

# Defaults (can be overridden by CLI args: python analyzer_md_csv.py <air.csv> <noise.csv>)
AIRQ_CSV_DEFAULT  = HERE / "airq_1min_fake.csv"
NOISE_CSV_DEFAULT = HERE / "noise_voice_1min_fake.csv"

# Output: single Markdown file in the same folder
SUMMARY_MD = HERE / "summary.md"

TZ_DEFAULT = "Europe/Madrid"

# Air endpoints and their test direction
AIR_VARS_CORE = {
    "CO2": "greater",
    "dCO2_mean3": "greater",
    "PM25": "greater",
    "PM10": "greater",
    "TEMP": "two-sided",
    "HUM": "two-sided",
}

PRIMARY_NOISE      = "voice_rate_time"
NOISE_VARS_PRIMARY = [PRIMARY_NOISE]
PRIMARY_ONLY       = True

LAGS_FOR_LEVELS  = list(range(0, 11))   # 0..10
LAGS_FOR_DERIVED = list(range(0, 21))   # 0..20
LAGS_NEG         = list(range(-10, 0))  # reverse sanity check

COVERAGE_MIN   = 0.50
MIN_SAMPLES    = 40
TRIM_Q         = 0.01
NEAR_CONST_EPS = 1e-12

ALPHA  = 0.05
CONF_Z = 1.959963984540054

PRES_HALFLIFE_MIN = 30.0  # for slow CO2 baseline

# ---------------------- Utilities ----------------------
def read_yaml(p: Path) -> dict:
    if p.exists() and yaml:
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def fix_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.replace("₂", "2") for c in df.columns]
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
    keep_noi = ["kit_code", "ts_min_utc", "voice_rate", "voice_rate_time",
                "intensity_mean", "voice_score_mean", "snr_mean", "sfm_mean",
                "frames", "coverage_rate"]
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
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    N = len(x)
    if N < 3:
        return (np.nan, np.nan, np.nan, 0.0, 0.0, 0.0, np.nan, np.nan)
    if np.var(x) < NEAR_CONST_EPS or np.var(y) < NEAR_CONST_EPS:
        return (np.nan, np.nan, np.nan, 0.0, 0.0, 0.0, np.nan, np.nan)
    r, _p2 = stats.pearsonr(x, y)
    r1x = lag1_autocorr(x); r1y = lag1_autocorr(y)
    denom = (1.0 + r1x * r1y)
    Neff = N if denom <= 0 else N * (1.0 - r1x * r1y) / denom
    Neff = float(np.clip(Neff, 3.0, N))
    df = max(1.0, Neff - 2.0)
    t = r * math.sqrt(df) / math.sqrt(max(1e-12, 1.0 - r*r))
    p2_adj = 2.0 * stats.t.sf(abs(t), df)
    return float(r), float(_p2), float(p2_adj), Neff, float(r1x), float(r1y), float(t), float(df)

def spearman_with_adj(x: np.ndarray, y: np.ndarray, Neff: float):
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 3 or np.var(x) < NEAR_CONST_EPS or np.var(y) < NEAR_CONST_EPS:
        return (np.nan, np.nan)
    rho, _p = stats.spearmanr(x, y)
    if not np.isfinite(rho) or Neff <= 3:
        return (float(rho) if np.isfinite(rho) else np.nan, np.nan)
    df = max(1.0, Neff - 2.0)
    t = rho * math.sqrt(df) / math.sqrt(max(1e-12, 1.0 - rho*rho))
    p2_adj = 2.0 * stats.t.sf(abs(t), df)
    return float(rho), float(p2_adj)

def p_from_alt(t: float, df: float, alt: str) -> float:
    if not np.isfinite(t) or df <= 0:
        return np.nan
    if alt == "two-sided":
        return 2.0 * stats.t.sf(abs(t), df)
    if alt == "greater":
        return stats.t.sf(t, df)
    if alt == "less":
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

# ---------- Presence-control helpers ----------
def lowpass_co2(co2: pd.Series, ts_utc: pd.Series, halflife_min: float = PRES_HALFLIFE_MIN) -> pd.Series:
    hl = float(halflife_min) if np.isfinite(halflife_min) and halflife_min > 0 else 30.0
    return co2.ewm(
        halflife=pd.Timedelta(minutes=hl),
        times=ts_utc,
        adjust=True,
        min_periods=3
    ).mean()

def cyclic_time_features(ts_utc: pd.Series, tz_local: str) -> pd.DataFrame:
    local = ts_utc.dt.tz_convert(tz_local)
    hod = local.dt.hour + local.dt.minute/60.0
    ang = 2*np.pi*hod/24.0
    return pd.DataFrame({"sin_hod": np.sin(ang), "cos_hod": np.cos(ang)})

def residualize(y: pd.Series, X: pd.DataFrame) -> pd.Series:
    X_ = X.copy()
    X_["intercept"] = 1.0
    m = y.notna()
    for c in X_.columns:
        m &= X_[c].notna()
    resid = pd.Series(index=y.index, dtype=float)
    if m.sum() < 10:
        return resid
    yv = y[m].values
    Xv = X_.loc[m].values
    beta, *_ = np.linalg.lstsq(Xv, yv, rcond=None)
    resid.loc[m] = yv - (Xv @ beta)
    return resid

# ---------------------- Lag scanner ----------------------
def scan_lags(df: pd.DataFrame, air_col: str, noise_col: str, lags: list[int], alt: str):
    rows = []
    xs_full = df[air_col].values
    ys_full = df[noise_col].values
    for L in lags:
        ys = pd.Series(ys_full).shift(L).values
        x, y = trim_xy(xs_full, ys_full if L == 0 else ys)
        if len(x) < MIN_SAMPLES:
            continue
        r, _p2raw, _p2a, Neff, r1x, r1y, tval, dfree = corr_with_adj(x, y)
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

# ---------------------- Pair runner ----------------------
def run_pair(air: pd.DataFrame, noise: pd.DataFrame, air_kit: str, noise_kit: str,
             tz_local: str, start_utc: str|None, end_utc: str|None,
             occ_cfg: dict, md_lines: list[str]):

    df = join_minutes(air, noise, air_kit, noise_kit)
    if df.empty:
        md_lines += [f"# Analysis Summary — {air_kit} × {noise_kit}", "", "_No overlapping minutes after join._"]
        return

    df = within_window(df, start_utc, end_utc)
    if df.empty:
        md_lines += [f"# Analysis Summary — {air_kit} × {noise_kit}", "", "_No data within requested window._"]
        return

    df = derive_air_features(df)
    df = filter_quality(df)

    # Occupancy proxy params
    base_q  = float(occ_cfg.get("base_quantile", 0.10))
    base_add= float(occ_cfg.get("base_add", 50.0))
    dco2_thr= float(occ_cfg.get("dco2_thresh", 1.5))
    df["occ_proxy"] = occ_proxy(df, base_quantile=base_q, base_add=base_add, dco2_thresh=dco2_thr)

    # Slow presence + diurnal
    df["CO2_lp"] = lowpass_co2(df["CO2"], df["ts_min_utc"], halflife_min=PRES_HALFLIFE_MIN)
    cyc = cyclic_time_features(df["ts_min_utc"], tz_local)
    df["sin_hod"] = cyc["sin_hod"]; df["cos_hod"] = cyc["cos_hod"]
    co2lp_med = float(np.nanmedian(df["CO2_lp"]))
    co2lp_std = float(np.nanstd(df["CO2_lp"]) + 1e-9)
    df["occ_level"] = (df["CO2_lp"] - co2lp_med) / co2lp_std

    noise_vars = [v for v in NOISE_VARS_PRIMARY if v in df.columns]
    if not noise_vars:
        md_lines += [f"# Analysis Summary — {air_kit} × {noise_kit}", "", "_No usable noise variables after join._"]
        return

    n_all = len(df)
    n_occ = int(df["occ_proxy"].sum())
    cov_mean_all = float(df.get("coverage_rate", pd.Series([np.nan]*n_all)).mean())
    cov_mean_occ = float(df[df["occ_proxy"]==1].get("coverage_rate", pd.Series([np.nan]*max(n_occ,1))).mean()) if n_occ>0 else np.nan

    results_rows = []
    neg_check = {"ALL": {}, "OCCUPIED": {}, "PRESENCE_CTRL": {}}

    def scope_block(tag: str, dfin: pd.DataFrame):
        if dfin.empty:
            return
        for air_var, alt in AIR_VARS_CORE.items():
            lags = LAGS_FOR_DERIVED if air_var in ("dCO2_mean3",) else LAGS_FOR_LEVELS
            family_rows, family_indices = [], []
            forward_rows_by_noise, reverse_rows_by_noise = {}, {}

            for noise_var in noise_vars:
                ok = dfin[[air_var, noise_var]].dropna()
                if len(ok) < MIN_SAMPLES:
                    continue
                rows_fwd = scan_lags(dfin, air_var, noise_var, lags, alt)
                if rows_fwd:
                    for r in rows_fwd: r["noise_var"] = noise_var
                    forward_rows_by_noise[noise_var] = rows_fwd
                    for i, row in enumerate(rows_fwd):
                        family_rows.append(row)
                        family_indices.append((noise_var, i))
                rows_rev = scan_lags(dfin, air_var, noise_var, LAGS_NEG, "two-sided")
                if rows_rev:
                    reverse_rows_by_noise[noise_var] = rows_rev

            if not family_rows:
                continue

            # BH-FDR across forward family
            pvals = [row["p_adj"] for row in family_rows]
            qvals = bh_fdr(pvals)
            for row, q in zip(family_rows, qvals):
                row["q_BH"] = float(q)
            for (noise_var, i), q in zip(family_indices, qvals):
                forward_rows_by_noise[noise_var][i]["q_BH"] = float(q)

            # Best forward by q, then p
            best = min(family_rows, key=lambda r: (r.get("q_BH", 1.0), r["p_adj"]))
            lo, hi = fisher_z_ci(best["r"], best["Neff"], CONF_Z)

            def _sign_ok(r, alt):
                if alt == "greater": return r > 0
                if alt == "less":    return r < 0
                return True

            decision = "Reject H0" if (best["q_BH"] <= ALPHA and _sign_ok(best["r"], alt)) else "Fail to reject H0"

            # Reverse diagnostic summary
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

    # Scopes
    scope_block("ALL", df)
    scope_block("OCCUPIED", df[df["occ_proxy"] == 1])

    d_occ = df[df["occ_proxy"] == 1].copy()
    if not d_occ.empty:
        X_ctrl = d_occ[["occ_level", "sin_hod", "cos_hod"]].copy()
        d_res = d_occ.copy()
        for air_var in AIR_VARS_CORE.keys():
            if air_var in d_res.columns:
                d_res[air_var] = residualize(d_occ[air_var], X_ctrl)
        for noise_var in noise_vars:
            if noise_var in d_res.columns:
                d_res[noise_var] = residualize(d_occ[noise_var], X_ctrl)
        scope_block("PRESENCE_CTRL", d_res)

    if not results_rows:
        md_lines += [
            f"# Analysis Summary — {air_kit} × {noise_kit}",
            "",
            "_No valid results after quality filters._"
        ]
        return

    res = pd.DataFrame(results_rows).sort_values(["scope", "air_var", "p_adj"])

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
            if not row: continue
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
            if d.empty: continue
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

    md_lines += [
        f"# Analysis Summary — {air_kit} × {noise_kit}",
        "",
        f"_Window_: {start_utc or 'ALL'} → {end_utc or 'ALL'}  •  _Timezone_: {tz_local}",
        f"_Minutes analysed (after quality filter)_: ALL={n_all}, OCCUPIED={n_occ}  •  Mean noise coverage: ALL={cov_mean_all:.2f}, OCC={cov_mean_occ:.2f}",
        "",
        "## Executive summary",
        f"- **Family-wise control:** BH-FDR across all tested lags per endpoint at α=0.05.",
        "- **Interpretation rule:** For one-sided endpoints (CO₂, ΔCO₂, PM), the sign must match the alternative.",
        ""
    ]
    if "ALL" in scopes_present:
        md_lines += ["### Key endpoints (ALL minutes)"] + bullets_for_scope("ALL") + [""]
    if "OCCUPIED" in scopes_present:
        md_lines += ["### Key endpoints (OCCUPIED minutes)"] + bullets_for_scope("OCCUPIED") + [""]
    if "PRESENCE_CTRL" in scopes_present:
        md_lines += ["### Presence-controlled (OCCUPIED residuals)",
                     "_Slow presence (low-pass CO₂) and daily rhythm removed from both Voice and Air before lag scan._"]
        md_lines += bullets_for_scope("PRESENCE_CTRL") + [""]

    md_lines += [
        "### Reverse-direction (negative-lag) diagnostics",
        "_Air leading Noise (-10…-1 min); not part of FDR family._",
        "**ALL:**"
    ] + neg_lines("ALL") + ["", "**OCCUPIED:**"] + neg_lines("OCCUPIED") + ["",
        "## Hypotheses by endpoint"
    ] + alt_statements() + ["",
        "## Variables",
        f"- **Noise (primary)**: `{PRIMARY_NOISE}`",
        "- **Air**: `CO2`, `dCO2_mean3` (3-min mean of ΔCO₂), `PM25`, `PM10`, `TEMP`, `HUM`",
        "",
        "## Methods (short)",
        "- **Pearson r** on aligned minute pairs after shifting Noise forward by lag L.",
        "- **Autocorrelation-aware testing:** estimate lag-1 autocorr for each series, derive an **effective N**, compute **t** and **p** with df = N_eff − 2.",
        "- **One-sided tests** implemented directly from t and df.",
        "- **FDR (BH)** across all forward lags per endpoint/scope → **q**; pick minimum-q lag (ties by p).",
        "- **95% CI** for r via **Fisher z** using N_eff.",
        "- **Reverse-direction** (negative lags) scanned and reported; excluded from FDR.",
        "- **Quality**: minutes require `coverage_rate ≥ 0.50` and ≥1 frame; window gating occurs pre-analysis.",
        f"- **Occupancy proxy** parameters: base_quantile={base_q}, base_add={base_add}, dCO2_thresh={dco2_thr}.",
        "- **Presence-controlled scope:** within OCCUPIED minutes, remove slow presence (low-pass CO₂, halflife 30 min) and daily rhythm (hour-of-day sine/cosine) from both Voice and Air, then re-run the same lag scan.",
        ""
    ]

def main():
    # Inputs from CLI or defaults (both CSV)
    if len(sys.argv) >= 3:
        air_csv = Path(sys.argv[1])
        noise_csv = Path(sys.argv[2])
    else:
        air_csv = AIRQ_CSV_DEFAULT
        noise_csv = NOISE_CSV_DEFAULT

    if not air_csv.exists() or not noise_csv.exists():
        sys.stderr.write(f"ERROR: CSV files not found:\n  {air_csv}\n  {noise_csv}\n")
        sys.exit(1)

    # Read CSVs
    air = pd.read_csv(air_csv)
    noise = pd.read_csv(noise_csv)
    air = fix_columns(air)
    noise = fix_columns(noise)

    # Optional YAML from the same folder
    cfg = read_yaml(HERE / "time_window_unified.yaml")
    tz_local = cfg.get("timezone", TZ_DEFAULT)
    start_utc = cfg.get("start_utc")
    end_utc   = cfg.get("end_utc")
    occ_cfg   = cfg.get("occ_proxy", {}) if isinstance(cfg, dict) else {}

    # Pairing (as in your original): match numeric tails, or fallback first-first
    air_kits   = sorted(air["kit_code"].dropna().unique()) if "kit_code" in air.columns else []
    noise_kits = sorted(noise["kit_code"].dropna().unique()) if "kit_code" in noise.columns else []

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
        sys.stderr.write("No kit pairs found to analyse.\n")
        sys.exit(1)

    # Build one Markdown with all pairs (usually you’ll have just one)
    md_lines: list[str] = []
    for ak, nk in pairs:
        run_pair(air, noise, ak, nk, tz_local, start_utc, end_utc, occ_cfg, md_lines)

    SUMMARY_MD.write_text("\n".join(md_lines).rstrip()+"\n", encoding="utf-8")
    print(f"Done. Wrote {SUMMARY_MD}")

if __name__ == "__main__":
    main()
