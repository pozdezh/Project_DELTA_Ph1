# analysis_airq_noise.py
# v4: constant-safe + full analysis + OCCWINDOW + OCCDAILY-inferred windows + autocorrelation-robust p-values (adj) + HAC
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

try:
    import statsmodels.api as sm
    HAS_SM = True
except Exception:
    HAS_SM = False

# ---------- CONFIG ----------
AIRQ_PARQ  = Path("data/processed/airq_1min.parquet")
NOISE_PARQ = Path("data/processed/noise_voice_1min.parquet")

PAIRS = [("AIRQ001", "NOISE102"), ("AIRQ002", "NOISE102")]

AIR_COLS = ["TEMP","HUM","CO2","PRES","LLUM","PM1","PM25","PM10"]
NOISE_COLS = [
    "voice_rate","voice_rate_time","intensity_mean","voice_score_mean",
    "snr_mean","sfm_mean","noiseRMS_mean","bandRMS_mean",
    "frames","voice_frames","frame_period_s","coverage_s","coverage_rate","voice_seconds"
]

PAIRS_TO_TEST = [
    ("CO2","voice_rate"),("PM25","voice_rate"),("PM10","voice_rate"),
    ("HUM","voice_rate"),("TEMP","voice_rate"),("CO2","snr_mean"),
]

LAGS_LEVEL_MIN     = list(range(0, 11))   # 0..10 min for level vars
LAGS_ROLLDIFF_MIN  = list(range(0, 21))   # 0..20 for roll/diff
VOICE_THRESH       = 0.05
MIN_N              = 30
FIG_DPI            = 140
plt.rcParams.update({"figure.autolayout": True})

# ===== Fixed occupied-hour windows (Europe/Madrid) =====
TZ = "Europe/Madrid"
OCC_LOCAL_WINDOWS = [
    ("2025-08-12", "09:00", "19:30"),
    ("2025-08-13", "09:00", "19:30"),
    ("2025-08-14", "09:00", "19:30"),
]

# ===== NEW: Auto-infer daily work windows (keeps all data; tags a daily block) =====
AUTO_INFER_WORK_WINDOWS = True
WORK_INFER = {
    "search_start_hour_min": 7,   # earliest plausible start
    "search_start_hour_max": 12,  # latest plausible start
    "search_end_hour_min": 15,    # earliest plausible end
    "search_end_hour_max": 22,    # latest plausible end
    "min_block_min": 60,          # minimum work block length to accept
    "margin_min": 30,             # +/- margin around inferred start/end when filtering
    "voice_smooth_thresh": 0.03,  # softer than VOICE_THRESH to detect quiet chatter
}
# -----------------------------------------------------------


def ensure_dirs():
    Path("reports").mkdir(parents=True, exist_ok=True)
    Path("data/processed").mkdir(parents=True, exist_ok=True)


def _fix_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: c.replace("₂", "2").strip() for c in df.columns})
    df["kit_code"] = df["kit_code"].astype(str).str.strip().str.upper()
    ts = pd.to_datetime(df["ts_min_utc"], utc=None, errors="coerce")
    if getattr(ts.dt, "tz", None) is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")
    df["ts_min_utc"] = ts.dt.floor("min")
    return df


def strict_time_join(air_df, noise_df, air_code, noise_code):
    A = (air_df[air_df["kit_code"] == air_code]
         [["ts_min_utc","kit_code"] + [c for c in AIR_COLS if c in air_df.columns]])
    N = (noise_df[noise_df["kit_code"] == noise_code]
         [["ts_min_utc"] + [c for c in NOISE_COLS if c in noise_df.columns]])
    if A.empty or N.empty:
        print(f"[MERGE {air_code}↔{noise_code}] empty side.")
        return pd.DataFrame()
    J = pd.merge(A, N, on="ts_min_utc", how="inner").sort_values("ts_min_utc").reset_index(drop=True)
    print(f"[MERGE {air_code}↔{noise_code}] rows = {len(J)}")
    return J


# ---------- Occupancy & ventilation ----------
def add_occupancy_and_ventilation_flags(df: pd.DataFrame, baseline_ppm: float | None = None) -> pd.DataFrame:
    d = df.sort_values("ts_min_utc").copy()
    if "CO2" in d.columns:
        d["CO2_roll5"] = d["CO2"].rolling(5, min_periods=3).mean()
        d["dCO2"] = d["CO2"].diff()
        d["dCO2_mean3"] = d["dCO2"].rolling(3, min_periods=2).mean()
    if "PM25" in d.columns:
        d["PM25_roll5"] = d["PM25"].rolling(5, min_periods=3).mean()
        d["dPM25"] = d["PM25"].diff()
    if "voice_rate" in d.columns:
        d["voice_rate_roll5"] = d["voice_rate"].rolling(5, min_periods=3).mean()

    if baseline_ppm is None and "CO2" in d.columns:
        baseline_ppm = float(d["CO2"].quantile(0.10))

    d["occ_proxy"] = 0
    if "CO2_roll5" in d.columns and "dCO2_mean3" in d.columns:
        d.loc[((d["CO2_roll5"] >= (baseline_ppm + 50)) | (d["dCO2_mean3"] > 1.5)), "occ_proxy"] = 1

    d["vent_on"] = 0
    if "dCO2_mean3" in d.columns:
        d.loc[(d["dCO2_mean3"] <= -3.0), "vent_on"] = 1

    return d


# ---------- helpers: constant-safe correlation ----------
def _valid_pair(sub_df: pd.DataFrame, a: str, n: str, min_n: int = MIN_N):
    sub = sub_df[[a, n]].dropna()
    if len(sub) < min_n:
        return None
    if sub[a].nunique(dropna=True) < 2 or sub[n].nunique(dropna=True) < 2:
        return None
    return sub[a].to_numpy(), sub[n].to_numpy()

def _log_skipped_pair(skipped_pairs: list, a: str, n: str, reason: str):
    skipped_pairs.append({"air_var": a, "noise_var": n, "reason": reason})


# ---------- NEW: autocorrelation-aware helpers ----------
def _lag1_autocorr(a: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    m = np.isfinite(a)
    a = a[m]
    if len(a) < 3:
        return 0.0
    x, y = a[:-1], a[1:]
    sx = np.std(x); sy = np.std(y)
    if sx == 0 or sy == 0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])

def _pearson_with_ac_adjustment(x: np.ndarray, y: np.ndarray):
    r, p_two = stats.pearsonr(x, y)
    N = len(x)
    rho1_x = _lag1_autocorr(x)
    rho1_y = _lag1_autocorr(y)
    denom = (1.0 + rho1_x * rho1_y)
    if denom <= 0:
        Neff = N
    else:
        Neff = N * (1.0 - rho1_x * rho1_y) / denom
    Neff = float(np.clip(Neff, 3.0, N))
    df = max(1, int(round(Neff - 2)))
    denom_t = max(1e-12, 1.0 - r**2)
    tstat = r * np.sqrt(df) / np.sqrt(denom_t)
    p_two_adj = 2.0 * stats.t.sf(np.abs(tstat), df)
    return r, p_two, float(p_two_adj), float(Neff), float(rho1_x), float(rho1_y)

def _one_sided_from_two_sided_adj(r: float, p_two_adj: float, direction: str = "greater") -> float:
    if direction == "greater":
        return p_two_adj / 2.0 if r >= 0 else 1.0 - (p_two_adj / 2.0)
    if direction == "less":
        return p_two_adj / 2.0 if r <= 0 else 1.0 - (p_two_adj / 2.0)
    return p_two_adj


# ---------- Correlations & heatmaps ----------
def corr_heatmaps(df: pd.DataFrame, outdir: Path):
    air_vars = [c for c in AIR_COLS if c in df.columns]
    noi_vars = [c for c in NOISE_COLS if c in df.columns]
    if not air_vars or not noi_vars:
        return

    pear = pd.DataFrame(index=air_vars, columns=noi_vars, dtype=float)
    spear = pd.DataFrame(index=air_vars, columns=noi_vars, dtype=float)
    skipped = []

    for a in air_vars:
        for n in noi_vars:
            pair = _valid_pair(df, a, n)
            if pair is None:
                _log_skipped_pair(skipped, a, n, "insufficient N or constant var")
                continue
            x, y = pair
            r, _ = stats.pearsonr(x, y)
            rho, _ = stats.spearmanr(x, y)
            pear.loc[a, n] = r
            spear.loc[a, n] = rho

    if skipped:
        pd.DataFrame(skipped).to_csv(outdir / "pairs_skipped_corr.csv", index=False)
    pear.to_csv(outdir / "corr_cross_pearson.csv")
    spear.to_csv(outdir / "corr_cross_spearman.csv")

    def heat(m, title, fpath):
        if m.dropna(how="all").empty:
            return
        fig, ax = plt.subplots(
            figsize=(max(6, 0.6 * len(m.columns)), max(4, 0.5 * len(m.index))), dpi=FIG_DPI
        )
        im = ax.imshow(m.astype(float).fillna(0), vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(len(m.columns))); ax.set_xticklabels(m.columns, rotation=45, ha="right")
        ax.set_yticks(range(len(m.index)));  ax.set_yticklabels(m.index)
        ax.set_title(title)
        plt.colorbar(im, ax=ax, shrink=0.8, label="Correlation")
        plt.savefig(fpath, dpi=FIG_DPI); plt.close(fig)

    heat(pear,  "Pearson cross-domain correlations", outdir / "corr_heatmap_pearson.png")
    heat(spear, "Spearman cross-domain correlations", outdir / "corr_heatmap_spearman.png")


# ---------- Lag scans (levels) ----------
def lag_scans_level(df: pd.DataFrame, outdir: Path):
    skipped = []
    for a, n in PAIRS_TO_TEST:
        if a not in df.columns or n not in df.columns:
            continue
        g = df[["ts_min_utc", a, n]].dropna().sort_values("ts_min_utc")
        if len(g) < MIN_N:
            _log_skipped_pair(skipped, a, n, "too few rows")
            continue
        g = g.set_index("ts_min_utc")
        res = []
        for L in LAGS_LEVEL_MIN:
            gg = g.copy()
            gg[n] = gg[n].shift(L)
            pair = _valid_pair(gg, a, n)
            if pair is None:
                continue
            x, y = pair
            r, p_classic, p_adj, Neff, r1x, r1y = _pearson_with_ac_adjustment(x, y)
            res.append({
                "air_var": a, "noise_var": n, "lag_min": L, "N": len(x),
                "pearson_r": r,
                "pearson_p": p_classic,
                "pearson_p_adj": p_adj,
                "Neff": Neff, "rho1_air": r1x, "rho1_noise": r1y
            })
        if res:
            out = pd.DataFrame(res)
            out["abs_r"] = out["pearson_r"].abs()
            out.sort_values(["abs_r", "N"], ascending=[False, False]).to_csv(
                outdir / f"lag_scan_{a}_vs_{n}.csv", index=False
            )
    if skipped:
        pd.DataFrame(skipped).to_csv(outdir / "pairs_skipped_lag_level.csv", index=False)


# ---------- Lag scans (rolling & diffs) ----------
def lag_scans_rolling_and_diff(df: pd.DataFrame, outdir: Path):
    pairs = []
    if "CO2_roll5" in df.columns and "voice_rate_roll5" in df.columns:
        pairs.append(("CO2_roll5", "voice_rate_roll5"))
    if "PM25_roll5" in df.columns and "voice_rate_roll5" in df.columns:
        pairs.append(("PM25_roll5", "voice_rate_roll5"))
    if "dCO2" in df.columns and "voice_rate" in df.columns:
        pairs.append(("dCO2", "voice_rate"))
    if "dPM25" in df.columns and "voice_rate" in df.columns:
        pairs.append(("dPM25", "voice_rate"))

    skipped = []
    for a, n in pairs:
        g = df[["ts_min_utc", a, n]].dropna().sort_values("ts_min_utc")
        if len(g) < 60:
            _log_skipped_pair(skipped, a, n, "too few rows for roll/diff")
            continue
        g = g.set_index("ts_min_utc")
        res = []
        for L in LAGS_ROLLDIFF_MIN:
            gg = g.copy()
            gg[n] = gg[n].shift(L)
            pair = _valid_pair(gg, a, n, min_n=30)
            if pair is None:
                continue
            x, y = pair
            r, p_classic, p_adj, Neff, r1x, r1y = _pearson_with_ac_adjustment(x, y)
            res.append({
                "air_var": a, "noise_var": n, "lag_min": L, "N": len(x),
                "pearson_r": r,
                "pearson_p": p_classic,
                "pearson_p_adj": p_adj,
                "Neff": Neff, "rho1_air": r1x, "rho1_noise": r1y
            })
        if res:
            out = pd.DataFrame(res)
            out["abs_r"] = out["pearson_r"].abs()
            out.sort_values(["abs_r", "N"], ascending=[False, False]).to_csv(
                outdir / f"lag_scan_{a}_vs_{n}.csv", index=False
            )
    if skipped:
        pd.DataFrame(skipped).to_csv(outdir / "pairs_skipped_lag_roll_diff.csv", index=False)


# ---------- Group tests ----------
def voice_group_tests(df: pd.DataFrame, outdir: Path):
    if "voice_rate" not in df.columns:
        return
    d = df.copy()
    d["voice_present"] = (d["voice_rate"] >= VOICE_THRESH).astype(int)
    rows = []
    for a in [c for c in ["CO2", "PM25", "PM10", "HUM", "TEMP"] if c in d.columns]:
        sub = d[[a, "voice_present"]].dropna()
        if sub["voice_present"].nunique() < 2:
            continue
        x = sub.loc[sub["voice_present"] == 1, a].values
        y = sub.loc[sub["voice_present"] == 0, a].values
        if len(x) < 10 or len(y) < 10:
            continue
        t, pt = stats.ttest_ind(x, y, equal_var=False)
        u, pu = stats.mannwhitneyu(x, y, alternative="two-sided")
        md = float(np.nanmean(x) - np.nanmean(y))
        sx2 = np.nanvar(x, ddof=1); sy2 = np.nanvar(y, ddof=1)
        d_eff = md / np.sqrt((sx2 + sy2) / 2.0) if (sx2 + sy2) > 0 else np.nan
        rows.append({"scope": "ALL", "air_var": a, "N_voice": len(x), "N_silent": len(y),
                     "mean_diff": md, "cohens_d": d_eff, "welch_p": pt, "mannwhitney_p": pu})
    if rows:
        pd.DataFrame(rows).to_csv(outdir / "group_tests_voice_vs_silent.csv", index=False)


def voice_group_tests_within_occupied(df: pd.DataFrame, outdir: Path, voice_var="voice_rate", thresh=VOICE_THRESH):
    if voice_var not in df.columns or "occ_proxy" not in df.columns:
        return
    d = df[(df["occ_proxy"] == 1)].copy()
    if d.empty:
        return
    d["voice_present"] = (d[voice_var] >= thresh).astype(int)
    rows = []
    for a in [c for c in ["CO2", "PM25", "PM10", "HUM", "TEMP", "dCO2"] if c in d.columns]:
        sub_all = d[[a, "voice_present", "vent_on"]].dropna()
        if sub_all["voice_present"].nunique() < 2:
            continue
        for scope, g in {"ALL": sub_all, "VENT_OFF": sub_all[sub_all["vent_on"] == 0],
                         "VENT_ON": sub_all[sub_all["vent_on"] == 1]}.items():
            if g["voice_present"].nunique() < 2:
                continue
            x = g.loc[g["voice_present"] == 1, a].values
            y = g.loc[g["voice_present"] == 0, a].values
            if len(x) < 10 or len(y) < 10:
                continue
            t, pt = stats.ttest_ind(x, y, equal_var=False)
            p_one = pt / 2 if np.nanmean(x) > np.nanmean(y) else 1 - (pt / 2)
            md = float(np.nanmean(x) - np.nanmean(y))
            sx2 = np.nanvar(x, ddof=1); sy2 = np.nanvar(y, ddof=1)
            d_eff = md / np.sqrt((sx2 + sy2) / 2.0) if (sx2 + sy2) > 0 else np.nan
            rows.append({"scope": scope, "air_var": a, "N_voice": len(x), "N_silent": len(y),
                         "mean_diff": md, "cohens_d": d_eff,
                         "welch_p_two_sided": pt, "welch_p_one_sided_gt": p_one})
    if rows:
        pd.DataFrame(rows).to_csv(outdir / "group_tests_voice_vs_silent_within_occupied.csv", index=False)


# ---------- Formal H0/H1 tests (full day) ----------
def one_sided_from_two_sided(r: float, p_two: float, direction: str) -> float:
    if direction == "greater":
        return p_two / 2 if r >= 0 else 1 - (p_two / 2)
    if direction == "less":
        return p_two / 2 if r <= 0 else 1 - (p_two / 2)
    return p_two

def formal_hypothesis_tests(df: pd.DataFrame, outdir: Path):
    tests = [
        {"air": "CO2",  "noise": "voice_rate", "lags": LAGS_LEVEL_MIN,    "alt": "greater",
         "H0": "No positive association between speaking and CO2 (ρ≤0)",
         "H1": "Speaking increases CO2 (ρ>0) at some lag within window"},
        {"air": "dCO2", "noise": "voice_rate", "lags": LAGS_ROLLDIFF_MIN, "alt": "greater",
         "H0": "No positive association between speaking and CO2 change rate (ρ≤0)",
         "H1": "Speaking increases CO2 rate (ρ>0) at some lag within window"},
        {"air": "PM25", "noise": "voice_rate", "lags": LAGS_LEVEL_MIN,    "alt": "greater",
         "H0": "No positive association between speaking and PM2.5 (ρ≤0)",
         "H1": "Speaking increases PM2.5 (ρ>0) at some lag within window"},
        {"air": "TEMP", "noise": "voice_rate", "lags": LAGS_LEVEL_MIN,    "alt": "two-sided",
         "H0": "No association between speaking and TEMP (ρ=0)",
         "H1": "Speaking affects TEMP (ρ≠0) at some lag within window"},
        {"air": "HUM",  "noise": "voice_rate", "lags": LAGS_LEVEL_MIN,    "alt": "two-sided",
         "H0": "No association between speaking and HUM (ρ=0)",
         "H1": "Speaking affects HUM (ρ≠0) at some lag within window"},
    ]

    rows, skipped = [], []
    for t in tests:
        a, n, alt = t["air"], t["noise"], t["alt"]
        if a not in df.columns or n not in df.columns:
            continue
        g = df[["ts_min_utc", a, n]].dropna().sort_values("ts_min_utc")
        if len(g) < MIN_N:
            _log_skipped_pair(skipped, a, n, "too few rows")
            continue
        g = g.set_index("ts_min_utc")
        best = None
        for L in t["lags"]:
            gg = g.copy()
            gg[n] = gg[n].shift(L)
            pair = _valid_pair(gg, a, n)
            if pair is None:
                continue
            x, y = pair
            r, p_two, p_two_adj, Neff, r1x, r1y = _pearson_with_ac_adjustment(x, y)
            score = r if alt == "greater" else abs(r)
            if (best is None) or (score > best["score"]):
                best = {"lag": L, "r": r, "p_two": p_two, "p_two_adj": p_two_adj,
                        "N": len(x), "Neff": Neff, "r1x": r1x, "r1y": r1y, "score": score}
        if best is None:
            _log_skipped_pair(skipped, a, n, "all lags invalid (constant or low N)")
            continue

        p_one_classic = one_sided_from_two_sided(best["r"], best["p_two"], "greater" if alt == "greater" else "two-sided")
        p_one_adj     = _one_sided_from_two_sided_adj(best["r"], best["p_two_adj"], "greater" if alt == "greater" else "two-sided")

        rows.append({
            "air_var": a, "noise_var": n, "alt": alt,
            "H0": t["H0"], "H1": t["H1"],
            "best_lag_min": best["lag"], "N": best["N"], "Neff": best["Neff"],
            "rho1_air": best["r1x"], "rho1_noise": best["r1y"],
            "pearson_r": best["r"],
            "p_two_sided": best["p_two"],
            "p_two_sided_adj": best["p_two_adj"],
            "p_one_sided_gt": (p_one_classic if alt == "greater" else np.nan),
            "p_one_sided_gt_adj": (p_one_adj if alt == "greater" else np.nan)
        })
    if rows:
        pd.DataFrame(rows).to_csv(outdir / "hypothesis_formal.csv", index=False)
    if skipped:
        pd.DataFrame(skipped).to_csv(outdir / "hypothesis_formal_skipped.csv", index=False)


# ===== Fixed OCCWINDOW helpers =====
def _filter_by_local_windows(df: pd.DataFrame, tz_name: str, windows):
    if df.empty:
        return df
    ts_local = df["ts_min_utc"].dt.tz_convert(tz_name)
    mask = pd.Series(False, index=df.index)
    for date_str, start_hhmm, end_hhmm in windows:
        start = pd.to_datetime(f"{date_str} {start_hhmm}", format="%Y-%m-%d %H:%M").tz_localize(tz_name)
        end   = pd.to_datetime(f"{date_str} {end_hhmm}",  format="%Y-%m-%d %H:%M").tz_localize(tz_name)
        mask |= (ts_local >= start) & (ts_local <= end)
    out = df.loc[mask].copy()
    if "occ_proxy" in out.columns:
        out = out[out["occ_proxy"] == 1].copy()
    return out

def formal_increase_hypotheses_occwindow(df: pd.DataFrame, outdir: Path):
    INCREASE_VARS = ["CO2","PM1","PM25","PM10","HUM","TEMP"]
    rows = []
    for a in INCREASE_VARS:
        if a not in df.columns or "voice_rate" not in df.columns:
            continue
        g = df[["ts_min_utc", a, "voice_rate"]].dropna().sort_values("ts_min_utc").set_index("ts_min_utc")
        best = None
        for L in LAGS_LEVEL_MIN:
            gg = g.copy(); gg["voice_rate"] = gg["voice_rate"].shift(L)
            pair = _valid_pair(gg, a, "voice_rate")
            if pair is None:
                continue
            x, y = pair
            r, p_two, p_two_adj, Neff, r1x, r1y = _pearson_with_ac_adjustment(x, y)
            if (best is None) or (r > best["r"]):
                best = {"lag": L, "r": r, "p_two": p_two, "p_two_adj": p_two_adj,
                        "N": len(x), "Neff": Neff, "r1x": r1x, "r1y": r1y}
        if best is None:
            continue
        p_one_classic = one_sided_from_two_sided(best["r"], best["p_two"], "greater")
        p_one_adj     = _one_sided_from_two_sided_adj(best["r"], best["p_two_adj"], "greater")
        rows.append({
            "air_var": a, "noise_var": "voice_rate", "alt": "greater",
            "H0": f"During/after speaking, {a} does not increase vs silent presence (Δ≤0)",
            "H1": f"During/after speaking, {a} increases vs silent presence (Δ>0)",
            "best_lag_min": best["lag"], "N": best["N"], "Neff": best["Neff"],
            "rho1_air": best["r1x"], "rho1_noise": best["r1y"],
            "pearson_r": best["r"],
            "p_two_sided": best["p_two"], "p_two_sided_adj": best["p_two_adj"],
            "p_one_sided_gt": p_one_classic, "p_one_sided_gt_adj": p_one_adj
        })

    if "dCO2" in df.columns and "voice_rate" in df.columns:
        g = df[["ts_min_utc","dCO2","voice_rate"]].dropna().sort_values("ts_min_utc").set_index("ts_min_utc")
        best = None
        for L in LAGS_ROLLDIFF_MIN:
            gg = g.copy(); gg["voice_rate"] = gg["voice_rate"].shift(L)
            pair = _valid_pair(gg, "dCO2", "voice_rate")
            if pair is None:
                continue
            x, y = pair
            r, p_two, p_two_adj, Neff, r1x, r1y = _pearson_with_ac_adjustment(x, y)
            if (best is None) or (r > best["r"]):
                best = {"lag": L, "r": r, "p_two": p_two, "p_two_adj": p_two_adj,
                        "N": len(x), "Neff": Neff, "r1x": r1x, "r1y": r1y}
        if best is not None:
            p_one_classic = one_sided_from_two_sided(best["r"], best["p_two"], "greater")
            p_one_adj     = _one_sided_from_two_sided_adj(best["r"], best["p_two_adj"], "greater")
            rows.append({
                "air_var": "dCO2", "noise_var": "voice_rate", "alt": "greater",
                "H0": "During/after speaking, CO2 change rate does not increase vs silent presence (Δ≤0)",
                "H1": "During/after speaking, CO2 change rate increases vs silent presence (Δ>0)",
                "best_lag_min": best["lag"], "N": best["N"], "Neff": best["Neff"],
                "rho1_air": best["r1x"], "rho1_noise": best["r1y"],
                "pearson_r": best["r"],
                "p_two_sided": best["p_two"], "p_two_sided_adj": best["p_two_adj"],
                "p_one_sided_gt": p_one_classic, "p_one_sided_gt_adj": p_one_adj
            })
    if rows:
        pd.DataFrame(rows).to_csv(outdir / "hypothesis_increase_OCCWINDOW.csv", index=False)

def voice_vs_silent_increase_occwindow(df: pd.DataFrame, outdir: Path):
    if "voice_rate" not in df.columns:
        return
    d = df.copy()
    d["voice_present"] = (d["voice_rate"] >= VOICE_THRESH).astype(int)
    rows = []
    for a in [x for x in ["CO2","PM1","PM25","PM10","HUM","TEMP","dCO2"] if x in d.columns]:
        sub = d[[a,"voice_present","vent_on"]].dropna()
        if sub["voice_present"].nunique() < 2:
            continue
        for scope, g in {"ALL": sub, "VENT_OFF": sub[sub["vent_on"]==0]}.items():
            if g["voice_present"].nunique() < 2:
                continue
            x = g.loc[g["voice_present"] == 1, a].values
            y = g.loc[g["voice_present"] == 0, a].values
            if len(x) < 10 or len(y) < 10:
                continue
            t, p_two = stats.ttest_ind(x, y, equal_var=False)
            p_one = p_two/2 if np.nanmean(x) > np.nanmean(y) else 1 - (p_two/2)

            hac_p_two = np.nan; hac_p_one = np.nan; coef = np.nan
            if HAS_SM:
                try:
                    X = sm.add_constant(g["voice_present"].to_numpy())
                    model = sm.OLS(g[a].to_numpy(), X, missing="drop").fit(
                        cov_type="HAC", cov_kwds={"maxlags": 4}
                    )
                    coef = float(model.params[1])
                    hac_p_two = float(model.pvalues[1])
                    hac_p_one = (hac_p_two/2.0) if coef > 0 else (1.0 - hac_p_two/2.0)
                except Exception:
                    pass

            rows.append({
                "air_var": a, "scope": scope,
                "N_voice": int((g["voice_present"]==1).sum()), "N_silent": int((g["voice_present"]==0).sum()),
                "mean_silent": float(np.nanmean(y)), "mean_voice": float(np.nanmean(x)),
                "mean_diff_voice_minus_silent": float(np.nanmean(x) - np.nanmean(y)),
                "welch_p_two_sided": float(p_two), "welch_p_one_sided_gt": float(p_one),
                "hac_coef_voice": coef, "hac_p_two_sided": hac_p_two, "hac_p_one_sided_gt": hac_p_one
            })
    if rows:
        pd.DataFrame(rows).to_csv(outdir / "group_voice_vs_silent_increase_OCCWINDOW.csv", index=False)


# ===== NEW: OCCDAILY (auto-inferred windows)
def infer_daily_work_windows(df: pd.DataFrame, tz_name: str, cfg: dict):
    if df.empty:
        return [], pd.Series(False, index=df.index)

    ts_local = df["ts_min_utc"].dt.tz_convert(tz_name)
    dloc = df.copy()
    dloc["ts_local"] = ts_local
    dloc["date"] = ts_local.dt.date
    dloc = dloc.sort_values("ts_local")

    start_min, start_max = cfg["search_start_hour_min"], cfg["search_start_hour_max"]
    end_min, end_max     = cfg["search_end_hour_min"], cfg["search_end_hour_max"]
    min_block            = pd.Timedelta(minutes=cfg["min_block_min"])
    margin               = pd.Timedelta(minutes=cfg["margin_min"])
    vth                  = cfg["voice_smooth_thresh"]

    # Occupancy signal (True when likely occupied): CO2-based OR smoothed low-level voice
    occ_sig = (dloc["occ_proxy"] == 1) | (dloc.get("voice_rate_roll5", pd.Series(0, index=dloc.index)).fillna(0.0) >= vth)
    dloc["_occ_sig"] = occ_sig.astype(bool)

    windows = []
    mask_any = pd.Series(False, index=df.index)

    for day, sub in dloc.groupby("date", as_index=False):
        daydf = sub.copy()
        # Limit search window in the day (e.g., 07:00–22:00)
        hod = daydf["ts_local"].dt.hour
        in_search = (hod >= start_min) & (hod <= end_max)
        daydf = daydf.loc[in_search].copy()
        if daydf.empty:
            continue

        # Run-length groups on _occ_sig
        daydf["_grp"] = (daydf["_occ_sig"] != daydf["_occ_sig"].shift()).cumsum()

        cand = []
        for g, gg in daydf.groupby("_grp"):
            if not bool(gg["_occ_sig"].iloc[0]):
                continue  # only True segments
            seg_start = gg["ts_local"].iloc[0]
            seg_end   = gg["ts_local"].iloc[-1]
            dur = seg_end - seg_start + pd.Timedelta(minutes=1)  # minute grid inclusive
            # Require segment to plausibly start in [start_min, start_max] and end in [end_min, end_max]
            if (start_min <= seg_start.hour <= start_max) or (start_min <= (seg_start + pd.Timedelta(minutes=15)).hour <= start_max):
                # end time plausibility is softer (people may stay late)
                if dur >= min_block:
                    cand.append((seg_start, seg_end, dur))

        if not cand:
            # fallback: pick the longest true segment in the day within search window
            for g, gg in daydf.groupby("_grp"):
                if not bool(gg["_occ_sig"].iloc[0]):
                    continue
                seg_start = gg["ts_local"].iloc[0]
                seg_end   = gg["ts_local"].iloc[-1]
                dur = seg_end - seg_start + pd.Timedelta(minutes=1)
                if dur >= min_block:
                    cand.append((seg_start, seg_end, dur))

        if not cand:
            continue

        # choose the longest candidate
        seg_start, seg_end, dur = sorted(cand, key=lambda t: t[2], reverse=True)[0]
        start_m = seg_start - margin
        end_m   = seg_end + margin

        windows.append({
            "date": str(day),
            "start_local": seg_start.isoformat(),
            "end_local": seg_end.isoformat(),
            "duration_min": int(dur.total_seconds() // 60),
            "start_margin_local": start_m.isoformat(),
            "end_margin_local": end_m.isoformat(),
            "margin_min": int(cfg["margin_min"])
        })

        # build mask for this day's margin window
        daymask = (ts_local >= start_m) & (ts_local <= end_m)
        mask_any = mask_any | daymask.reindex(mask_any.index, fill_value=False)

    return windows, mask_any


# ---------- Optional simple OLS ----------
def ols_best_lag(df: pd.DataFrame, outdir: Path, air_var="CO2", noise_var="voice_rate", use_diff=False):
    if not HAS_SM or air_var not in df.columns or noise_var not in df.columns:
        return
    g = df[["ts_min_utc", air_var, noise_var, "vent_on"]].dropna().sort_values("ts_min_utc")
    if len(g) < MIN_N:
        return
    g = g.set_index("ts_min_utc")
    best = None
    for L in (LAGS_ROLLDIFF_MIN if use_diff else LAGS_LEVEL_MIN):
        gg = g.copy()
        gg[noise_var] = gg[noise_var].shift(L)
        sub = gg[[air_var, noise_var, "vent_on"]].dropna()
        if len(sub) < MIN_N or sub[noise_var].nunique() < 2 or sub[air_var].nunique() < 2:
            continue
        r, _ = stats.pearsonr(sub[air_var], sub[noise_var])
        if best is None or abs(r) > abs(best["r"]):
            best = {"lag": L, "r": r, "N": len(sub)}
    if best is None:
        return
    gg = g.copy()
    gg[noise_var] = gg[noise_var].shift(best["lag"])
    sub = gg[[air_var, noise_var, "vent_on"]].dropna()
    if sub[noise_var].nunique() < 2 or sub[air_var].nunique() < 2:
        return
    X = sm.add_constant(sub[[noise_var, "vent_on"]].values)
    y = sub[air_var].values
    try:
        model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    except Exception:
        model = sm.OLS(y, X).fit()
    with open(outdir / f"ols_{air_var}_vs_{noise_var}_lag{best['lag']}.txt", "w", encoding="utf-8") as f:
        f.write(model.summary().as_text())


# ---------- Runner ----------
def run_dataset(df: pd.DataFrame, tag: str):
    outdir = Path("reports") / tag
    outdir.mkdir(parents=True, exist_ok=True)
    if df.empty:
        print(f"[DATASET {tag}] EMPTY")
        return

    # Occupancy & ventilation; rolling & diffs
    df = add_occupancy_and_ventilation_flags(df)

    # Save merged parquet
    out_parq = Path("data/processed") / f"airq_noise_merged_{tag}.parquet"
    df.to_parquet(out_parq, index=False)
    print(f"[DATASET {tag}] rows={len(df)} span={df['ts_min_utc'].min()}→{df['ts_min_utc'].max()}  saved={out_parq}")

    # FULL-DAY analyses (unchanged)
    corr_heatmaps(df, outdir)
    lag_scans_level(df, outdir)
    lag_scans_rolling_and_diff(df, outdir)
    voice_group_tests(df, outdir)
    voice_group_tests_within_occupied(df, outdir)
    formal_hypothesis_tests(df, outdir)

    # ===== Fixed OCCWINDOW block (unchanged)
    df_occ = _filter_by_local_windows(df, TZ, OCC_LOCAL_WINDOWS)  # local 09:00–19:30 & occ_proxy==1
    occdir = outdir / "OCCWINDOW"
    occdir.mkdir(parents=True, exist_ok=True)
    if not df_occ.empty:
        formal_increase_hypotheses_occwindow(df_occ, occdir)
        voice_vs_silent_increase_occwindow(df_occ, occdir)
    else:
        (occdir / "EMPTY.txt").write_text("No rows in occupied-time window after occupancy filter.\n", encoding="utf-8")

    # ===== NEW: OCCDAILY inferred work windows (+/- margin), but keep nights/off-hours in main analysis
    if AUTO_INFER_WORK_WINDOWS:
        occdaily_dir = outdir / "OCCDAILY"
        occdaily_dir.mkdir(parents=True, exist_ok=True)
        windows, mask = infer_daily_work_windows(df, TZ, WORK_INFER)
        if windows:
            pd.DataFrame(windows).to_csv(occdaily_dir / "inferred_windows.csv", index=False)
            # Filter to rows inside any day's margin window AND occupied (silent or speaking)
            df_inferred = df.loc[mask].copy()
            if "occ_proxy" in df_inferred.columns:
                df_inferred = df_inferred[df_inferred["occ_proxy"] == 1].copy()
            if not df_inferred.empty:
                formal_increase_hypotheses_occwindow(df_inferred, occdaily_dir)
                voice_vs_silent_increase_occwindow(df_inferred, occdaily_dir)
            else:
                (occdaily_dir / "EMPTY.txt").write_text("No rows after inferred-window & occupancy filter.\n", encoding="utf-8")
        else:
            (occdaily_dir / "EMPTY.txt").write_text("No inferred work windows detected.\n", encoding="utf-8")

    # Optional OLS at best lag (levels and slope)
    ols_best_lag(df, outdir, air_var="CO2", noise_var="voice_rate", use_diff=False)
    if "dCO2" in df.columns:
        ols_best_lag(df, outdir, air_var="dCO2", noise_var="voice_rate", use_diff=True)


def main():
    ensure_dirs()
    air = _fix_cols(pd.read_parquet(AIRQ_PARQ))
    noise = _fix_cols(pd.read_parquet(NOISE_PARQ))

    merged_parts = []
    for air_code, noise_code in PAIRS:
        print(f"\n=== {air_code} ↔ {noise_code} ===")
        m = strict_time_join(air, noise, air_code, noise_code)
        if m.empty:
            continue
        m["pair_tag"] = f"{air_code}_{noise_code}"
        run_dataset(m, f"{air_code}_{noise_code}")
        merged_parts.append(m)

    if merged_parts:
        combined = pd.concat(merged_parts, ignore_index=True)
        run_dataset(combined, "COMBINED")
    else:
        print("\n[END] All merges empty (unexpected given your checks).")

if __name__ == "__main__":
    main()

