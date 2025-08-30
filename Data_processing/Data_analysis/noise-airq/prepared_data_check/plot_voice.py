#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Plot voice activity over time from noise_voice_1min.parquet.

Outputs:
- reports/plots/voice_timeline_<KIT>.png        (full span)
- reports/plots/voice_timeline_<KIT>_<DATE>.png (per-day panels)
- reports/plots/voice_segments_<KIT>.csv        (detected speaking segments)

What it shows:
- voice_rate_time (0..1) per minute
- 5-min rolling mean (smoother)
- Reference thresholds (0.05, 0.20)
- Shading where data coverage is low (coverage_rate < 0.9)
- Optional intensity overlay (secondary axis)

Tip:
- voice_rate_time is the most robust indicator (“fraction of the minute with speech”),
  automatically accounting for partial coverage.
"""

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ------------ CONFIG (edit as needed) ------------
NOISE_PARQ = Path("data/processed/noise_voice_1min.parquet")
OUT_DIR    = Path("reports/plots")
KIT_CODE   = "NOISE102"     # which noise kit to plot
TZ_LOCAL   = "Europe/Madrid"

THRESHOLDS       = [0.05, 0.20]  # light & stricter reference lines
SMOOTH_MIN       = 5             # minutes for rolling mean
MIN_SEGMENT_MIN  = 2             # minimum contiguous minutes above threshold to call a "segment"
COVERAGE_WARN    = 0.90          # shade minutes with coverage_rate below this
PLOT_INTENSITY   = True          # overlay intensity_mean on a secondary axis
# -------------------------------------------------


def load_noise(path: Path, kit: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    # Normalize basics
    df["kit_code"] = df["kit_code"].astype(str).str.upper().str.strip()
    df = df[df["kit_code"] == kit].copy()
    if df.empty:
        raise SystemExit(f"[ERROR] No rows for kit_code={kit} in {path}")
    # Ensure tz-aware UTC
    ts = pd.to_datetime(df["ts_min_utc"], errors="coerce")
    if getattr(ts.dt, "tz", None) is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")
    df["ts_min_utc"] = ts.dt.floor("min")
    # Local time for labeling
    df["ts_min_local"] = df["ts_min_utc"].dt.tz_convert(TZ_LOCAL)
    df = df.sort_values("ts_min_utc").reset_index(drop=True)
    return df


def build_voice_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    # Fallbacks if columns missing
    if "voice_rate_time" not in d.columns and "voice_rate" in d.columns and "coverage_s" in d.columns:
        # voice_seconds / coverage_s; if coverage=0 -> 0
        cov = d["coverage_s"].replace(0, np.nan)
        d["voice_rate_time"] = (d.get("voice_seconds", 0.0) / cov).fillna(0.0)
    elif "voice_rate_time" not in d.columns and "voice_rate" in d.columns:
        d["voice_rate_time"] = d["voice_rate"].astype(float)
    # Smooth series (rolling window)
    d["voice_time_roll"] = d["voice_rate_time"].rolling(SMOOTH_MIN, min_periods=max(2, SMOOTH_MIN//2)).mean()
    # Helpful QA flags
    d["low_coverage"] = (d.get("coverage_rate", 1.0) < COVERAGE_WARN).astype(int)
    return d


def contiguous_segments(ts: pd.Series, flag: pd.Series, min_len=2) -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    """
    Return list of (start_ts, end_ts, length_minutes) for contiguous True regions in flag.
    """
    if flag.empty:
        return []
    # Ensure aligned and sorted
    s = flag.astype(bool).reset_index(drop=True)
    t = ts.reset_index(drop=True)
    # Find run starts/ends
    edges = s.ne(s.shift(fill_value=False))
    group_ids = edges.cumsum()
    segs = []
    for g, gg in s.groupby(group_ids):
        if not bool(gg.iloc[0]):
            continue
        idx = gg.index
        length = len(idx)
        if length >= min_len:
            segs.append((t.loc[idx[0]], t.loc[idx[-1]], length))
    return segs


def plot_full_span(d: pd.DataFrame, kit: str):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(14, 4.5), dpi=140)

    # Voice rate time & rolling
    ax.plot(d["ts_min_local"], d["voice_rate_time"], lw=0.8, label="voice_rate_time (per min)")
    ax.plot(d["ts_min_local"], d["voice_time_roll"], lw=1.6, label=f"rolling mean ({SMOOTH_MIN} min)")

    # Thresholds
    for th in THRESHOLDS:
        ax.axhline(th, linestyle="--", linewidth=1, alpha=0.7)

    # Coverage shading
    if "low_coverage" in d.columns and d["low_coverage"].any():
        # mark low coverage with light vertical shading
        lows = d[d["low_coverage"] == 1]["ts_min_local"]
        for t in lows:
            ax.axvspan(t, t + pd.Timedelta(minutes=1), alpha=0.10)

    ax.set_ylim(-0.02, 1.02)
    ax.set_ylabel("Voice fraction of minute (0..1)")
    ax.set_title(f"Voice activity timeline — {kit}")
    ax.legend(loc="upper right", ncol=2)
    ax.grid(True, which="both", axis="both", alpha=0.25)

    # Optional intensity overlay
    if PLOT_INTENSITY and "intensity_mean" in d.columns:
        ax2 = ax.twinx()
        ax2.plot(d["ts_min_local"], d["intensity_mean"], lw=0.8, alpha=0.6)
        ax2.set_ylabel("Intensity (mean rise dB proxy)")

    fpath = OUT_DIR / f"voice_timeline_{kit}.png"
    plt.savefig(fpath, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"[PLOT] full-span → {fpath}")


def plot_per_day_panels(d: pd.DataFrame, kit: str):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for day, g in d.groupby(d["ts_min_local"].dt.date):
        fig, ax = plt.subplots(figsize=(14, 3.8), dpi=140)

        ax.plot(g["ts_min_local"], g["voice_rate_time"], lw=0.8, label="voice_rate_time")
        ax.plot(g["ts_min_local"], g["voice_time_roll"], lw=1.6, label=f"rolling {SMOOTH_MIN}m")

        for th in THRESHOLDS:
            ax.axhline(th, linestyle="--", linewidth=1, alpha=0.7)

        # shade low coverage
        if "low_coverage" in g.columns and g["low_coverage"].any():
            lows = g[g["low_coverage"] == 1]["ts_min_local"]
            for t in lows:
                ax.axvspan(t, t + pd.Timedelta(minutes=1), alpha=0.10)

        ax.set_ylim(-0.02, 1.02)
        ax.set_ylabel("Voice fraction (0..1)")
        ax.set_title(f"{kit} — {day}")
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.25)

        if PLOT_INTENSITY and "intensity_mean" in g.columns:
            ax2 = ax.twinx()
            ax2.plot(g["ts_min_local"], g["intensity_mean"], lw=0.8, alpha=0.6)
            ax2.set_ylabel("Intensity")

        fpath = OUT_DIR / f"voice_timeline_{kit}_{day}.png"
        plt.savefig(fpath, dpi=160, bbox_inches="tight")
        plt.close(fig)
        print(f"[PLOT] per-day → {fpath}")


def detect_and_export_segments(d: pd.DataFrame, kit: str):
    """
    Detect speaking segments where the smoothed voice fraction exceeds THRESHOLDS[0]
    for at least MIN_SEGMENT_MIN minutes.
    """
    th = THRESHOLDS[0]
    flag = (d["voice_time_roll"].fillna(0) >= th)
    segs = contiguous_segments(d["ts_min_local"], flag, min_len=MIN_SEGMENT_MIN)
    if not segs:
        print("[SEGMENTS] none detected")
        return
    rows = []
    for s, e, L in segs:
        rows.append({
            "kit_code": kit,
            "start_local": s.isoformat(),
            "end_local": (e + pd.Timedelta(minutes=1)).isoformat(),  # inclusive minute
            "duration_min": L
        })
    out_csv = OUT_DIR / f"voice_segments_{kit}.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"[SEGMENTS] {len(rows)} segments → {out_csv}")


def main():
    d0 = load_noise(NOISE_PARQ, KIT_CODE)
    d  = build_voice_features(d0)

    # Basic stats
    minutes_with_voice = int((d["voice_rate_time"] >= THRESHOLDS[0]).sum())
    total_minutes = len(d)
    print(f"[INFO] Minutes with voice ≥ {THRESHOLDS[0]:.2f}: {minutes_with_voice}/{total_minutes} "
          f"({100*minutes_with_voice/total_minutes:.1f}%)")

    # Plots
    plot_full_span(d, KIT_CODE)
    plot_per_day_panels(d, KIT_CODE)

    # Segments CSV
    detect_and_export_segments(d, KIT_CODE)


if __name__ == "__main__":
    main()
