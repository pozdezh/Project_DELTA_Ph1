# Analysis Summary — AIRQ002 × NOISE102

_Window_: ALL → ALL  •  _Timezone_: Europe/Madrid
_Minutes analysed (after quality filter)_: ALL=3345, OCCUPIED=2794  •  Mean noise coverage: ALL=1.00, OCC=1.00

## Executive summary
- **Family-wise control:** BH-FDR across all tested lags per endpoint at α=0.05.
- **Interpretation rule:** For one-sided endpoints (CO₂, ΔCO₂, PM), the sign must match the alternative.

### Key endpoints (ALL minutes)
• **CO2:** ✓ best lag **+10 min**, r=+0.121 (95% CI [+0.070, +0.171]), r²=0.015, q=2.16e-05, N_eff/N=1451/3196
• **dCO2_mean3:** ✓ best lag **+6 min**, r=+0.156 (95% CI [+0.108, +0.204]), r²=0.024, q=2.44e-09, N_eff/N=1590/3142
• **PM25:** ✗ best lag **+8 min**, r=+0.045 (95% CI [-0.015, +0.105]), r²=0.002, q=0.323, N_eff/N=1078/1920
• **PM10:** ✗ best lag **+8 min**, r=+0.044 (95% CI [-0.016, +0.103]), r²=0.002, q=0.325, N_eff/N=1079/1921
• **TEMP:** ✓ best lag **+2 min**, r=-0.185 (95% CI [-0.234, -0.135]), r²=0.034, q=3.25e-12, N_eff/N=1463/3255
• **HUM:** ✗ best lag **+8 min**, r=+0.036 (95% CI [-0.015, +0.087]), r²=0.001, q=0.381, N_eff/N=1495/3250

### Key endpoints (OCCUPIED minutes)
• **CO2:** ✓ best lag **+10 min**, r=+0.168 (95% CI [+0.109, +0.225]), r²=0.028, q=1.39e-07, N_eff/N=1091/2698
• **dCO2_mean3:** ✓ best lag **+6 min**, r=+0.155 (95% CI [+0.100, +0.209]), r²=0.024, q=1.92e-07, N_eff/N=1231/2623
• **PM25:** ✗ best lag **+0 min**, r=+0.017 (95% CI [-0.056, +0.090]), r²=0.000, q=0.687, N_eff/N=720/1609
• **PM10:** ✗ best lag **+0 min**, r=+0.017 (95% CI [-0.056, +0.090]), r²=0.000, q=0.676, N_eff/N=721/1610
• **TEMP:** ✓ best lag **+2 min**, r=-0.191 (95% CI [-0.247, -0.134]), r²=0.037, q=6.27e-10, N_eff/N=1109/2716
• **HUM:** ✗ best lag **+8 min**, r=+0.011 (95% CI [-0.047, +0.070]), r²=0.000, q=0.994, N_eff/N=1124/2711

### Reverse-direction (negative-lag) diagnostics
_Air leading Noise (-10…-1 min); not part of FDR family._
**ALL:**
• **CO2:** reverse check max |r|=0.100 at lag -4 min (noise=voice_rate_time)
• **dCO2_mean3:** reverse check max |r|=0.165 at lag -4 min (noise=voice_rate_time)
• **PM25:** reverse check max |r|=0.050 at lag -10 min (noise=voice_rate_time)
• **PM10:** reverse check max |r|=0.047 at lag -10 min (noise=voice_rate_time)
• **TEMP:** reverse check max |r|=0.181 at lag -1 min (noise=voice_rate_time)
• **HUM:** reverse check max |r|=0.038 at lag -4 min (noise=voice_rate_time)

**OCCUPIED:**
• **CO2:** reverse check max |r|=0.118 at lag -1 min (noise=voice_rate_time)
• **dCO2_mean3:** reverse check max |r|=0.189 at lag -5 min (noise=voice_rate_time)
• **PM25:** reverse check max |r|=0.036 at lag -10 min (noise=voice_rate_time)
• **PM10:** reverse check max |r|=0.035 at lag -10 min (noise=voice_rate_time)
• **TEMP:** reverse check max |r|=0.190 at lag -2 min (noise=voice_rate_time)
• **HUM:** reverse check max |r|=0.039 at lag -8 min (noise=voice_rate_time)

## Hypotheses by endpoint
- **CO2** — Alt: **greater**  •  H₀: corr ≤ 0  •  H₁: corr > 0
- **dCO2_mean3** — Alt: **greater**  •  H₀: corr ≤ 0  •  H₁: corr > 0
- **PM25** — Alt: **greater**  •  H₀: corr ≤ 0  •  H₁: corr > 0
- **PM10** — Alt: **greater**  •  H₀: corr ≤ 0  •  H₁: corr > 0
- **TEMP** — Alt: **two-sided**  •  H₀: corr = 0  •  H₁: corr ≠ 0
- **HUM** — Alt: **two-sided**  •  H₀: corr = 0  •  H₁: corr ≠ 0

## Variables
- **Noise (primary)**: `voice_rate_time`
- **Air**: `CO2`, `dCO2_mean3` (3-min mean of ΔCO₂), `PM25`, `PM10`, `TEMP`, `HUM`

## Best-lag details (per scope & endpoint)
_Shows the best-performing Noise variable and lag for each air endpoint._

### ALL

| Air | Alt | Noise | Lag+min | r | r² | 95% CI | Neff/N | p_adj | q_BH | Decision |
|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| CO2 | greater | voice_rate_time | +10 | +0.121 | 0.015 | [+0.070, +0.171] | 1451/3196 | 1.96e-06 | 2.16e-05 | Reject H0 |
| dCO2_mean3 | greater | voice_rate_time | +6 | +0.156 | 0.024 | [+0.108, +0.204] | 1590/3142 | 1.81e-10 | 2.44e-09 | Reject H0 |
| PM25 | greater | voice_rate_time | +8 | +0.045 | 0.002 | [-0.015, +0.105] | 1078/1920 | 0.0689 | 0.323 | Fail to reject H0 |
| PM10 | greater | voice_rate_time | +8 | +0.044 | 0.002 | [-0.016, +0.103] | 1079/1921 | 0.0747 | 0.325 | Fail to reject H0 |
| TEMP | two-sided | voice_rate_time | +2 | -0.185 | 0.034 | [-0.234, -0.135] | 1463/3255 | 1e-12 | 3.25e-12 | Reject H0 |
| HUM | two-sided | voice_rate_time | +8 | +0.036 | 0.001 | [-0.015, +0.087] | 1495/3250 | 0.163 | 0.381 | Fail to reject H0 |

### OCCUPIED

| Air | Alt | Noise | Lag+min | r | r² | 95% CI | Neff/N | p_adj | q_BH | Decision |
|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| CO2 | greater | voice_rate_time | +10 | +0.168 | 0.028 | [+0.109, +0.225] | 1091/2698 | 1.26e-08 | 1.39e-07 | Reject H0 |
| dCO2_mean3 | greater | voice_rate_time | +6 | +0.155 | 0.024 | [+0.100, +0.209] | 1231/2623 | 2.31e-08 | 1.92e-07 | Reject H0 |
| PM25 | greater | voice_rate_time | +0 | +0.017 | 0.000 | [-0.056, +0.090] | 720/1609 | 0.324 | 0.687 | Fail to reject H0 |
| PM10 | greater | voice_rate_time | +0 | +0.017 | 0.000 | [-0.056, +0.090] | 721/1610 | 0.323 | 0.676 | Fail to reject H0 |
| TEMP | two-sided | voice_rate_time | +2 | -0.191 | 0.037 | [-0.247, -0.134] | 1109/2716 | 1.36e-10 | 6.27e-10 | Reject H0 |
| HUM | two-sided | voice_rate_time | +8 | +0.011 | 0.000 | [-0.047, +0.070] | 1124/2711 | 0.709 | 0.994 | Fail to reject H0 |

## Methods (short)
- **Pearson r** on aligned minute pairs after shifting Noise forward by lag L.
- **Autocorrelation-aware testing:** estimate lag-1 autocorr for each series, derive an **effective N** (N_eff), compute **t** and **p** with df = N_eff − 2 (real-valued).
- **One-sided tests** implemented directly from t and df (no halving of two-sided p).
- **FDR (BH)** across all forward lags per endpoint/scope → **q**; we pick the minimum-q lag (ties by p).
- **95% CI** for r via **Fisher z** using N_eff; we also report **r²** as effect size.
- **Reverse-direction** (negative lags) scanned and reported for plausibility; excluded from FDR.
- **Spearman ρ** reported in per-lag CSVs as a robustness check; not used in decisions.
- **Quality**: minutes require `coverage_rate ≥ 0.50` and ≥1 frame; window gating occurs pre-analysis.
- **Occupancy proxy** parameters: base_quantile=0.1, base_add=50.0, dCO2_thresh=1.5.
