# analyze_reports.py
from pathlib import Path
import pandas as pd
import numpy as np
import json

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
        return pd.DataFrame()

def _find_datasets():
    if not REPORTS_DIR.exists():
        return []
    ds = []
    for child in REPORTS_DIR.iterdir():
        if child.is_dir():
            if (child / "hypothesis_formal.csv").exists() or (child / "OCCWINDOW").exists() or (child / "OCCDAILY").exists():
                ds.append(child.name)
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

def _fmt_p(p):
    if pd.isna(p): return "n/a"
    if p < 1e-4: return f"{p:.1e}"
    return f"{p:.4f}"

def _decision_full(row):
    """For full-day hypothesis_formal.csv rows"""
    if row.get("alt") == "greater":
        p = row.get("p_one_sided_gt")
        return "Reject H0" if pd.notna(p) and p < ALPHA else "Fail to reject H0"
    else:
        p = row.get("p_two_sided")
        return "Reject H0" if pd.notna(p) and p < ALPHA else "Fail to reject H0"

def _decision_occ_increase_from_p(p):
    return "Reject H0" if pd.notna(p) and p < ALPHA else "Fail to reject H0"

def _pick_group_p(row: pd.Series):
    """
    Prefer HAC one-sided p if present; otherwise Welch one-sided.
    Returns (p_value, source_str).
    """
    hac = row.get("hac_p_one_sided_gt")
    if pd.notna(hac):
        return float(hac), "HAC"
    w = row.get("welch_p_one_sided_gt")
    return (float(w) if pd.notna(w) else np.nan), "Welch"

def _add_group_rows(scope_prefix: str, df: pd.DataFrame, dataset_tag: str):
    rows = []
    if df.empty: 
        return rows
    for _, r in df.iterrows():
        p_use, p_src = _pick_group_p(r)
        decision = _decision_occ_increase_from_p(p_use)
        N = int(r.get("N_voice", 0) + r.get("N_silent", 0))
        rows.append({
            "dataset": dataset_tag,
            "scope": f"{scope_prefix}:{r['scope']}",
            "air_var": r["air_var"],
            "alt": "greater",
            "best_lag_min": np.nan,
            "pearson_r": np.nan,
            "N": N,
            "p_value": p_use,
            "p_source": p_src,
            "decision": decision,
            "mean_diff": r.get("mean_diff_voice_minus_silent"),
            "mean_voice": r.get("mean_voice"),
            "mean_silent": r.get("mean_silent")
        })
    return rows

def _top_corr_pairs(base: Path, top_k: int = 6):
    pear = _safe_read_csv(base / "corr_cross_pearson.csv")
    spear = _safe_read_csv(base / "corr_cross_spearman.csv")
    out = {}
    if not pear.empty:
        p = pear.set_index(pear.columns[0])
        p = p.apply(pd.to_numeric, errors="coerce")
        stack = p.stack(dropna=True).rename("r").reset_index()
        stack.columns = ["air_var", "noise_var", "r"]
        stack["abs_r"] = stack["r"].abs()
        out["pearson_top"] = stack.sort_values("abs_r", ascending=False).head(top_k).to_dict(orient="records")
    else:
        out["pearson_top"] = []
    if not spear.empty:
        s = spear.set_index(spear.columns[0])
        s = s.apply(pd.to_numeric, errors="coerce")
        stack = s.stack(dropna=True).rename("rho").reset_index()
        stack.columns = ["air_var", "noise_var", "rho"]
        stack["abs_rho"] = stack["rho"].abs()
        out["spearman_top"] = stack.sort_values("abs_rho", ascending=False).head(top_k).to_dict(orient="records")
    else:
        out["spearman_top"] = []
    return out

# ---------- core per-dataset aggregation ----------
def summarize_dataset(tag: str) -> dict:
    base = REPORTS_DIR / tag

    # Full-day hypotheses
    full_hyp = _safe_read_csv(base / "hypothesis_formal.csv")

    # OCCWINDOW: occupied fixed local windows
    occ_hyp  = _safe_read_csv(base / "OCCWINDOW" / "hypothesis_increase_OCCWINDOW.csv")
    occ_group = _safe_read_csv(base / "OCCWINDOW" / "group_voice_vs_silent_increase_OCCWINDOW.csv")

    # OCCDAILY: auto-inferred work windows (+/- margin)
    occdaily_hyp   = _safe_read_csv(base / "OCCDAILY" / "hypothesis_increase_OCCWINDOW.csv")
    occdaily_group = _safe_read_csv(base / "OCCDAILY" / "group_voice_vs_silent_increase_OCCWINDOW.csv")

    # Lag scan context (full-day files)
    lag_co2  = _best_lag_from_csv(base / "lag_scan_CO2_vs_voice_rate.csv")
    lag_dco2 = _best_lag_from_csv(base / "lag_scan_dCO2_vs_voice_rate.csv")

    # Top correlations
    corr_tops = _top_corr_pairs(base, top_k=6)

    out_rows = []

    # 1) Full-day formal tests
    if not full_hyp.empty:
        for _, r in full_hyp.iterrows():
            p_val = r["p_one_sided_gt"] if r["alt"] == "greater" else r["p_two_sided"]
            out_rows.append({
                "dataset": tag, "scope": "FULL",
                "air_var": r["air_var"], "alt": r["alt"],
                "best_lag_min": r["best_lag_min"],
                "pearson_r": r["pearson_r"], "N": r["N"],
                "p_value": p_val, "decision": _decision_full(r)
            })

    # 2) OCCWINDOW increase tests
    if not occ_hyp.empty:
        for _, r in occ_hyp.iterrows():
            out_rows.append({
                "dataset": tag, "scope": "OCCWINDOW",
                "air_var": r["air_var"], "alt": "greater",
                "best_lag_min": r["best_lag_min"],
                "pearson_r": r["pearson_r"], "N": r["N"],
                "p_value": r["p_one_sided_gt"],
                "decision": _decision_occ_increase_from_p(r["p_one_sided_gt"])
            })

    # 3) OCCDAILY increase tests
    if not occdaily_hyp.empty:
        for _, r in occdaily_hyp.iterrows():
            out_rows.append({
                "dataset": tag, "scope": "OCCDAILY",
                "air_var": r["air_var"], "alt": "greater",
                "best_lag_min": r["best_lag_min"],
                "pearson_r": r["pearson_r"], "N": r["N"],
                "p_value": r["p_one_sided_gt"],
                "decision": _decision_occ_increase_from_p(r["p_one_sided_gt"])
            })

    # 4) Group tests (voice vs silent) for OCCWINDOW and OCCDAILY
    out_rows.extend(_add_group_rows("OCCWINDOW", occ_group, tag))
    out_rows.extend(_add_group_rows("OCCDAILY", occdaily_group, tag))

    # 5) Human-readable Markdown summary
    md_lines = [f"### {tag}"]

    # Priority: OCCWINDOW > OCCDAILY > FULL for the headline CO2 items
    def _headline_line(scope_name: str, hyp_df: pd.DataFrame, var: str, label: str):
        if hyp_df.empty: 
            return False
        sub = hyp_df[hyp_df["air_var"] == var]
        if sub.empty: 
            return False
        r = sub.iloc[0]
        md_lines.append(
            f"- **{label} ({scope_name}):** best lag **{int(r['best_lag_min'])} min**, "
            f"r={r['pearson_r']:.3f} (p={_fmt_p(r['p_one_sided_gt'])}) → "
            f"**{_decision_occ_increase_from_p(r['p_one_sided_gt'])}**."
        )
        return True

    if not _headline_line("occupied hours", occ_hyp, "CO2", "CO₂"):
        if not _headline_line("inferred work hours", occdaily_hyp, "CO2", "CO₂"):
            if not full_hyp.empty:
                co2_full = full_hyp[full_hyp["air_var"] == "CO2"]
                if not co2_full.empty:
                    r = co2_full.iloc[0]
                    p = r["p_one_sided_gt"] if r["alt"] == "greater" else r["p_two_sided"]
                    md_lines.append(
                        f"- **CO₂ (full day):** best lag **{int(r['best_lag_min'])} min**, "
                        f"r={r['pearson_r']:.3f} (p={_fmt_p(p)}) → **{_decision_full(r)}**."
                    )

    # ΔCO2 analogous
    if not _headline_line("occupied", occ_hyp, "dCO2", "ΔCO₂"):
        if not _headline_line("inferred work hours", occdaily_hyp, "dCO2", "ΔCO₂"):
            if not full_hyp.empty:
                dco2_full = full_hyp[full_hyp["air_var"] == "dCO2"]
                if not dco2_full.empty:
                    r = dco2_full.iloc[0]
                    md_lines.append(
                        f"- **ΔCO₂ (full day):** best lag **{int(r['best_lag_min'])} min**, "
                        f"r={r['pearson_r']:.3f} (p={_fmt_p(r['p_one_sided_gt'])}) → **{_decision_full(r)}**."
                    )

    # PMs (occupied/inferred if available)
    for pm, label in [("PM25","PM2.5"), ("PM10","PM10"), ("PM1","PM1")]:
        done = False
        for scope_name, hyp_df in [("occupied", occ_hyp), ("inferred work hours", occdaily_hyp)]:
            sub = hyp_df[hyp_df["air_var"] == pm] if not hyp_df.empty else pd.DataFrame()
            if not sub.empty:
                r = sub.iloc[0]
                md_lines.append(
                    f"- **{label} ({scope_name}):** best lag **{int(r['best_lag_min'])} min**, "
                    f"r={r['pearson_r']:.3f} (p={_fmt_p(r['p_one_sided_gt'])}) → "
                    f"**{_decision_occ_increase_from_p(r['p_one_sided_gt'])}**."
                )
                done = True
                break
        if not done and not full_hyp.empty:
            sub = full_hyp[full_hyp["air_var"] == pm]
            if not sub.empty:
                r = sub.iloc[0]
                p = r["p_one_sided_gt"] if r["alt"] == "greater" else r["p_two_sided"]
                md_lines.append(
                    f"- **{label} (full day):** best lag **{int(r['best_lag_min'])} min**, "
                    f"r={r['pearson_r']:.3f} (p={_fmt_p(p)}) → **{_decision_full(r)}**."
                )

    # TEMP & HUM (note possible full-day decrease)
    for var in ["TEMP","HUM"]:
        msg_done = False
        for scope_name, hyp_df in [("occupied", occ_hyp), ("inferred work hours", occdaily_hyp)]:
            sub = hyp_df[hyp_df["air_var"] == var] if not hyp_df.empty else pd.DataFrame()
            if not sub.empty:
                r = sub.iloc[0]
                md_lines.append(
                    f"- **{var} ({scope_name}):** best lag **{int(r['best_lag_min'])} min**, "
                    f"r={r['pearson_r']:.3f} (p={_fmt_p(r['p_one_sided_gt'])}) → "
                    f"**{_decision_occ_increase_from_p(r['p_one_sided_gt'])}**."
                )
                msg_done = True
                break
        if not msg_done and not full_hyp.empty:
            fsub = full_hyp[full_hyp["air_var"] == var]
            if not fsub.empty:
                fr = fsub.iloc[0]
                note = ""
                if pd.notna(fr.get("p_two_sided")) and fr["p_two_sided"] < ALPHA and fr["pearson_r"] < 0:
                    note = f" (Full-day suggests **decrease**: r={fr['pearson_r']:.3f}, p={_fmt_p(fr['p_two_sided'])})."
                p = fr["p_two_sided"]
                md_lines.append(
                    f"- **{var} (full day):** best lag **{int(fr['best_lag_min'])} min**, "
                    f"r={fr['pearson_r']:.3f} (p={_fmt_p(p)}) → **{_decision_full(fr)}**{note}"
                )

    # Voice vs silent (occupied): show CO2 for ALL and VENT_OFF, prefer HAC p if present
    def _group_bullets(scope_prefix: str, gdf: pd.DataFrame):
        if gdf.empty:
            return
        co2 = gdf[gdf["air_var"] == "CO2"]
        for scope in ["ALL", "VENT_OFF"]:
            gg = co2[co2["scope"] == scope]
            if not gg.empty:
                r = gg.iloc[0]
                p_use, p_src = _pick_group_p(r)
                md_lines.append(
                    f"- **CO₂ voice vs silent ({scope_prefix}:{scope}):** "
                    f"Δmean = {r['mean_diff_voice_minus_silent']:.2f} "
                    f"(voice {r['mean_voice']:.2f} − silent {r['mean_silent']:.2f}), "
                    f"one-sided p={_fmt_p(p_use)} [{p_src}] → "
                    f"**{_decision_occ_increase_from_p(p_use)}**."
                )

    _group_bullets("OCCWINDOW", occ_group)
    _group_bullets("OCCDAILY", occdaily_group)

    # Lag-scan context
    if lag_co2:
        L, rr, NN = lag_co2
        md_lines.append(f"- **Context (full-day CO₂ lag scan):** top |r| at **{L} min**, r={rr:.3f}, N={NN}.")
    if lag_dco2:
        L, rr, NN = lag_dco2
        md_lines.append(f"- **Context (full-day ΔCO₂ lag scan):** top |r| at **{L} min**, r={rr:.3f}, N={NN}.")

    # Top cross-domain correlations (Pearson/Spearman)
    if corr_tops["pearson_top"]:
        items = [f"{x['air_var']}↔{x['noise_var']} (r={x['r']:.3f})"
                 for x in corr_tops["pearson_top"][:4]]
        md_lines.append(f"- **Top cross Pearson (|r|):** " + "; ".join(items) + ".")
    if corr_tops["spearman_top"]:
        items = [f"{x['air_var']}↔{x['noise_var']} (ρ={x['rho']:.3f})"
                 for x in corr_tops["spearman_top"][:4]]
        md_lines.append(f"- **Top cross Spearman (|ρ|):** " + "; ".join(items) + ".")

    return {
        "table_rows": out_rows,
        "markdown": "\n".join(md_lines),
        "corr_tops": corr_tops
    }

# ---------- main ----------
def main():
    datasets = _find_datasets()
    if not datasets:
        print("No reports/* datasets found. Run the analysis first.")
        return

    all_rows = []
    md_blocks = ["# Noise ↔ Air Quality: Conclusions\n"]
    json_snapshot = {}

    for tag in datasets:
        s = summarize_dataset(tag)
        all_rows.extend(s["table_rows"])
        md_blocks.append(s["markdown"])
        md_blocks.append("")
        json_snapshot[tag] = {
            "rows": s["table_rows"],
            "corr_tops": s["corr_tops"]
        }

    out_df = pd.DataFrame(all_rows)
    out_csv = REPORTS_DIR / "summary_conclusions.csv"
    out_df.to_csv(out_csv, index=False)

    # Console: decisions for headline scopes only
    to_show = out_df[out_df["scope"].isin(["FULL","OCCWINDOW","OCCDAILY"])][
        ["dataset","scope","air_var","best_lag_min","pearson_r","N","p_value","decision"]
    ]
    if not to_show.empty:
        print("\n=== DECISIONS (FULL, OCCWINDOW, OCCDAILY) ===")
        pd.set_option("display.float_format", lambda x: f"{x:.6f}")
        print(to_show.sort_values(["dataset","scope","air_var"]).to_string(index=False))
        pd.reset_option("display.float_format")

    md_path = REPORTS_DIR / "summary_conclusions.md"
    md = "\n".join(md_blocks)
    md_path.write_text(md, encoding="utf-8")

    json_path = REPORTS_DIR / "summary_conclusions.json"
    json_path.write_text(json.dumps(json_snapshot, indent=2), encoding="utf-8")

    print(f"\nSaved CSV  → {out_csv}")
    print(f"Saved MD   → {md_path}")
    print(f"Saved JSON → {json_path}")

if __name__ == "__main__":
    main()
