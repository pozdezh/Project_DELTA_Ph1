# analyze_reports.py
from pathlib import Path
import pandas as pd
import numpy as np
import textwrap

ALPHA = 0.05
REPORTS_DIR = Path("reports")
DATASETS_DEFAULT = ["AIRQ001_NOISE102", "AIRQ002_NOISE102", "COMBINED"]

# ---------- helpers ----------
def _safe_read_csv(p: Path) -> pd.DataFrame:
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p)
    except Exception:
        # sometimes csvs may be empty or corrupted – handle gracefully
        return pd.DataFrame()

def _find_datasets():
    if not REPORTS_DIR.exists():
        return []
    # detect folders that look like datasets (have hypothesis_formal.csv or OCCWINDOW)
    ds = []
    for child in REPORTS_DIR.iterdir():
        if child.is_dir():
            if (child / "hypothesis_formal.csv").exists() or (child / "OCCWINDOW").exists():
                ds.append(child.name)
    # preserve default order if present
    ordered = [d for d in DATASETS_DEFAULT if d in ds]
    remaining = [d for d in ds if d not in ordered]
    return ordered + sorted(remaining)

def _best_lag_from_csv(path: Path):
    df = _safe_read_csv(path)
    if df.empty or "pearson_r" not in df.columns:
        return None
    df["abs_r"] = df["pearson_r"].abs()
    row = df.sort_values(["abs_r", "N"], ascending=[False, False]).iloc[0]
    return int(row.get("lag_min", np.nan)), float(row["pearson_r"]), int(row.get("N", np.nan))

def _effect_word_r(r: float) -> str:
    a = abs(r)
    if a < 0.05: return "very weak"
    if a < 0.10: return "weak"
    if a < 0.20: return "small"
    if a < 0.30: return "moderate"
    return "large"

def _effect_word_d(d: float) -> str:
    if np.isnan(d): return "n/a"
    a = abs(d)
    if a < 0.2: return "very small"
    if a < 0.5: return "small"
    if a < 0.8: return "medium"
    return "large"

def _decision_full(row):
    """For full-day hypothesis_formal.csv rows"""
    if row.get("alt") == "greater":
        p = row.get("p_one_sided_gt")
        return "Reject H0" if pd.notna(p) and p < ALPHA else "Fail to reject H0"
    else:
        p = row.get("p_two_sided")
        return "Reject H0" if pd.notna(p) and p < ALPHA else "Fail to reject H0"

def _decision_occ_increase(row):
    """For OCCWINDOW hypothesis_increase_OCCWINDOW.csv rows (one-sided 'greater')"""
    p = row.get("p_one_sided_gt")
    return "Reject H0" if pd.notna(p) and p < ALPHA else "Fail to reject H0"

def _fmt_p(p):
    if pd.isna(p): return "n/a"
    if p < 1e-4: return f"{p:.1e}"
    return f"{p:.4f}"

# ---------- core per-dataset aggregation ----------
def summarize_dataset(tag: str) -> dict:
    base = REPORTS_DIR / tag

    # Full-day hypotheses
    full_hyp = _safe_read_csv(base / "hypothesis_formal.csv")
    # OCCWINDOW hypotheses (increase only, within occupied local windows)
    occ_hyp  = _safe_read_csv(base / "OCCWINDOW" / "hypothesis_increase_OCCWINDOW.csv")
    # Voice vs silent within occupied window
    occ_group = _safe_read_csv(base / "OCCWINDOW" / "group_voice_vs_silent_increase_OCCWINDOW.csv")

    # Best-lag scans for CO2 and dCO2 (full-day, for context)
    lag_co2 = _best_lag_from_csv(base / "lag_scan_CO2_vs_voice_rate.csv")
    lag_dco2 = _best_lag_from_csv(base / "lag_scan_dCO2_vs_voice_rate.csv")

    out_rows = []

    # 1) Full-day: record all formal tests
    if not full_hyp.empty:
        for _, r in full_hyp.iterrows():
            out_rows.append({
                "dataset": tag,
                "scope": "FULL",
                "air_var": r["air_var"],
                "alt": r["alt"],
                "best_lag_min": r["best_lag_min"],
                "pearson_r": r["pearson_r"],
                "N": r["N"],
                "p_value": r["p_one_sided_gt"] if r["alt"] == "greater" else r["p_two_sided"],
                "decision": _decision_full(r),
            })

    # 2) OCCWINDOW: one-sided “increase vs silent”
    if not occ_hyp.empty:
        for _, r in occ_hyp.iterrows():
            out_rows.append({
                "dataset": tag,
                "scope": "OCCWINDOW",
                "air_var": r["air_var"],
                "alt": "greater",
                "best_lag_min": r["best_lag_min"],
                "pearson_r": r["pearson_r"],
                "N": r["N"],
                "p_value": r["p_one_sided_gt"],
                "decision": _decision_occ_increase(r),
            })

    # 3) OCCWINDOW group: voice vs silent (ALL, VENT_OFF), one-sided p-values
    group_rows = []
    if not occ_group.empty:
        for _, r in occ_group.iterrows():
            group_rows.append({
                "dataset": tag,
                "scope": f"OCCWINDOW:{r['scope']}",
                "air_var": r["air_var"],
                "alt": "greater",
                "best_lag_min": np.nan,
                "pearson_r": np.nan,
                "N": int(r["N_voice"] + r["N_silent"]),
                "p_value": r["welch_p_one_sided_gt"],
                "decision": "Reject H0" if r["welch_p_one_sided_gt"] < ALPHA else "Fail to reject H0",
                "mean_diff": r["mean_diff_voice_minus_silent"],
                "mean_voice": r["mean_voice"],
                "mean_silent": r["mean_silent"],
            })

    # 4) Build a human summary paragraph for the dataset
    md_lines = [f"### {tag}"]
    # CO2 conclusions
    co2_full = full_hyp[full_hyp["air_var"] == "CO2"] if not full_hyp.empty else pd.DataFrame()
    co2_occ  = occ_hyp[occ_hyp["air_var"] == "CO2"]   if not occ_hyp.empty else pd.DataFrame()
    if not co2_occ.empty:
        r = co2_occ.iloc[0]
        md_lines.append(
            f"- **CO₂ (occupied hours):** best lag **{int(r['best_lag_min'])} min**, r={r['pearson_r']:.3f} "
            f"(p={_fmt_p(r['p_one_sided_gt'])}) → **{_decision_occ_increase(r)}**."
        )
    elif not co2_full.empty:
        r = co2_full.iloc[0]
        p = r["p_one_sided_gt"] if r["alt"] == "greater" else r["p_two_sided"]
        md_lines.append(
            f"- **CO₂ (full day):** best lag **{int(r['best_lag_min'])} min**, r={r['pearson_r']:.3f} "
            f"(p={_fmt_p(p)}) → **{_decision_full(r)}**."
        )
    # dCO2
    dco2_full = full_hyp[full_hyp["air_var"] == "dCO2"] if not full_hyp.empty else pd.DataFrame()
    dco2_occ  = occ_hyp[occ_hyp["air_var"] == "dCO2"]   if not occ_hyp.empty else pd.DataFrame()
    if not dco2_occ.empty:
        r = dco2_occ.iloc[0]
        md_lines.append(
            f"- **ΔCO₂ (occupied):** best lag **{int(r['best_lag_min'])} min**, r={r['pearson_r']:.3f} "
            f"(p={_fmt_p(r['p_one_sided_gt'])}) → **{_decision_occ_increase(r)}**."
        )
    elif not dco2_full.empty:
        r = dco2_full.iloc[0]; p = r["p_one_sided_gt"]
        md_lines.append(
            f"- **ΔCO₂ (full day):** best lag **{int(r['best_lag_min'])} min**, r={r['pearson_r']:.3f} "
            f"(p={_fmt_p(p)}) → **{_decision_full(r)}**."
        )
    # PM2.5 / PM10
    for pm in ["PM25","PM10","PM1"]:
        o = occ_hyp[occ_hyp["air_var"] == pm] if not occ_hyp.empty else pd.DataFrame()
        if not o.empty:
            r = o.iloc[0]
            md_lines.append(
                f"- **{pm} (occupied):** best lag **{int(r['best_lag_min'])} min**, r={r['pearson_r']:.3f} "
                f"(p={_fmt_p(r['p_one_sided_gt'])}) → **{_decision_occ_increase(r)}**."
            )
    # TEMP & HUM – note: OCC test is “increase”; if it fails but full-day 2-sided shows opposite, call that out
    for var in ["TEMP","HUM"]:
        o = occ_hyp[occ_hyp["air_var"] == var] if not occ_hyp.empty else pd.DataFrame()
        f = full_hyp[full_hyp["air_var"] == var] if not full_hyp.empty else pd.DataFrame()
        if not o.empty:
            r = o.iloc[0]
            line = (
                f"- **{var} (occupied):** best lag **{int(r['best_lag_min'])} min**, r={r['pearson_r']:.3f} "
                f"(p={_fmt_p(r['p_one_sided_gt'])}) → **{_decision_occ_increase(r)}**."
            )
            # If we failed to reject increase, but full-day shows significant negative (TEMP case), add note
            if _decision_occ_increase(r) == "Fail to reject H0" and not f.empty:
                fr = f.iloc[0]
                if pd.notna(fr["p_two_sided"]) and fr["p_two_sided"] < ALPHA and fr["pearson_r"] < 0:
                    line += f" (Full-day suggests **decrease**: r={fr['pearson_r']:.3f}, p={_fmt_p(fr['p_two_sided'])})."
            md_lines.append(line)
        elif not f.empty:
            fr = f.iloc[0]
            p = fr["p_two_sided"]
            md_lines.append(
                f"- **{var} (full day):** best lag **{int(fr['best_lag_min'])} min**, r={fr['pearson_r']:.3f} "
                f"(p={_fmt_p(p)}) → **{_decision_full(fr)}**."
            )

    # Voice vs silent (occupied) – CO2 most interesting; show ALL and VENT_OFF
    if not occ_group.empty:
        g = occ_group[occ_group["air_var"] == "CO2"]
        for scope in ["ALL","VENT_OFF"]:
            gg = g[g["scope"] == scope]
            if not gg.empty:
                r = gg.iloc[0]
                md_lines.append(
                    f"- **CO₂ voice vs silent ({scope}):** Δmean = {r['mean_diff_voice_minus_silent']:.2f} "
                    f"(voice {r['mean_voice']:.2f} − silent {r['mean_silent']:.2f}), "
                    f"one-sided p={_fmt_p(r['welch_p_one_sided_gt'])} → "
                    f"**{'Reject H0' if r['welch_p_one_sided_gt'] < ALPHA else 'Fail to reject H0'}**."
                )

    # Add lag context line if present
    if lag_co2:
        L, rr, NN = lag_co2
        md_lines.append(f"- **Context (full-day CO₂ lag scan):** top |r| at **{L} min**, r={rr:.3f}, N={NN}.")
    if lag_dco2:
        L, rr, NN = lag_dco2
        md_lines.append(f"- **Context (full-day ΔCO₂ lag scan):** top |r| at **{L} min**, r={rr:.3f}, N={NN}.")

    return {
        "table_rows": out_rows + group_rows,
        "markdown": "\n".join(md_lines)
    }

# ---------- main ----------
def main():
    datasets = _find_datasets()
    if not datasets:
        print("No reports/* datasets found. Run the analysis first.")
        return

    all_rows = []
    md_blocks = ["# Noise ↔ Air Quality: Conclusions\n"]

    for tag in datasets:
        s = summarize_dataset(tag)
        all_rows.extend(s["table_rows"])
        md_blocks.append(s["markdown"])
        md_blocks.append("")

    # Save tidy CSV
    out_df = pd.DataFrame(all_rows)
    out_csv = REPORTS_DIR / "summary_conclusions.csv"
    out_df.to_csv(out_csv, index=False)

    # Pretty console print for decisions only (FULL+OCCWINDOW hypotheses)
    to_show = out_df[
        out_df["scope"].isin(["FULL","OCCWINDOW"])
    ][["dataset","scope","air_var","best_lag_min","pearson_r","N","p_value","decision"]]
    if not to_show.empty:
        print("\n=== DECISIONS (FULL & OCCWINDOW) ===")
        # Avoid scientific notation flooding
        pd.set_option("display.float_format", lambda x: f"{x:.6f}")
        print(to_show.sort_values(["dataset","scope","air_var"]).to_string(index=False))
        pd.reset_option("display.float_format")

    # Save markdown
    md_path = REPORTS_DIR / "summary_conclusions.md"
    md = "\n".join(md_blocks)
    md_path.write_text(md, encoding="utf-8")

    print(f"\nSaved CSV → {out_csv}")
    print(f"Saved MD  → {md_path}")

if __name__ == "__main__":
    main()
