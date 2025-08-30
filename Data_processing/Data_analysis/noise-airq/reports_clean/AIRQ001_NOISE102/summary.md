# Analysis Summary — AIRQ001 × NOISE102

_Window_: ALL → ALL  •  _Timezone_: Europe/Madrid
_Minutes analysed (after quality filter)_: ALL=3345, OCCUPIED=2804  •  Mean noise coverage: ALL=1.00, OCC=1.00

## Executive summary
- **Family-wise control:** BH-FDR across all tested lags per endpoint at α=0.05.
- **Interpretation rule:** For one-sided endpoints (CO₂, ΔCO₂, PM), the sign must match the alternative.

### Key endpoints (ALL minutes)
• **CO2:** ✓ best lag **+10 min**, r=+0.114 (95% CI [+0.062, +0.165]), r²=0.013, q=4.29e-05, N_eff/N=1410/3196
• **dCO2_mean3:** ✓ best lag **+2 min**, r=+0.172 (95% CI [+0.124, +0.219]), r²=0.030, q=4.64e-11, N_eff/N=1599/3145
• **PM25:** ✗ best lag **+8 min**, r=+0.060 (95% CI [-0.001, +0.121]), r²=0.004, q=0.17, N_eff/N=1028/1921
• **PM10:** ✗ best lag **+8 min**, r=+0.060 (95% CI [-0.002, +0.120]), r²=0.004, q=0.183, N_eff/N=1028/1921
• **TEMP:** ✓ best lag **+10 min**, r=-0.179 (95% CI [-0.228, -0.128]), r²=0.032, q=9.78e-11, N_eff/N=1434/3246
• **HUM:** ✓ best lag **+10 min**, r=+0.083 (95% CI [+0.034, +0.132]), r²=0.007, q=0.00973, N_eff/N=1599/3245

### Key endpoints (OCCUPIED minutes)
• **CO2:** ✓ best lag **+10 min**, r=+0.157 (95% CI [+0.101, +0.213]), r²=0.025, q=4.13e-07, N_eff/N=1155/2710
• **dCO2_mean3:** ✓ best lag **+2 min**, r=+0.188 (95% CI [+0.133, +0.242]), r²=0.035, q=4.52e-10, N_eff/N=1209/2635
• **PM25:** ✗ best lag **+8 min**, r=+0.030 (95% CI [-0.039, +0.099]), r²=0.001, q=0.413, N_eff/N=806/1609
• **PM10:** ✗ best lag **+8 min**, r=+0.031 (95% CI [-0.038, +0.100]), r²=0.001, q=0.417, N_eff/N=807/1611
• **TEMP:** ✓ best lag **+7 min**, r=-0.162 (95% CI [-0.219, -0.104]), r²=0.026, q=1.32e-07, N_eff/N=1110/2724
• **HUM:** ✗ best lag **+8 min**, r=+0.047 (95% CI [-0.011, +0.103]), r²=0.002, q=0.329, N_eff/N=1179/2721

### Reverse-direction (negative-lag) diagnostics
_Air leading Noise (-10…-1 min); not part of FDR family._
**ALL:**
• **CO2:** reverse check max |r|=0.101 at lag -2 min (noise=voice_rate_time)
• **dCO2_mean3:** reverse check max |r|=0.160 at lag -4 min (noise=voice_rate_time)
• **PM25:** reverse check max |r|=0.055 at lag -10 min (noise=voice_rate_time)
• **PM10:** reverse check max |r|=0.052 at lag -10 min (noise=voice_rate_time)
• **TEMP:** reverse check max |r|=0.169 at lag -1 min (noise=voice_rate_time)
• **HUM:** reverse check max |r|=0.080 at lag -1 min (noise=voice_rate_time)

**OCCUPIED:**
• **CO2:** reverse check max |r|=0.126 at lag -1 min (noise=voice_rate_time)
• **dCO2_mean3:** reverse check max |r|=0.193 at lag -4 min (noise=voice_rate_time)
• **PM25:** reverse check max |r|=0.032 at lag -10 min (noise=voice_rate_time)
• **PM10:** reverse check max |r|=0.030 at lag -10 min (noise=voice_rate_time)
• **TEMP:** reverse check max |r|=0.160 at lag -3 min (noise=voice_rate_time)
• **HUM:** reverse check max |r|=0.039 at lag -1 min (noise=voice_rate_time)

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
| CO2 | greater | voice_rate_time | +10 | +0.114 | 0.013 | [+0.062, +0.165] | 1410/3196 | 8.7e-06 | 4.29e-05 | Reject H0 |
| dCO2_mean3 | greater | voice_rate_time | +2 | +0.172 | 0.030 | [+0.124, +0.219] | 1599/3145 | 2.21e-12 | 4.64e-11 | Reject H0 |
| PM25 | greater | voice_rate_time | +8 | +0.060 | 0.004 | [-0.001, +0.121] | 1028/1921 | 0.0263 | 0.17 | Fail to reject H0 |
| PM10 | greater | voice_rate_time | +8 | +0.060 | 0.004 | [-0.002, +0.120] | 1028/1921 | 0.0282 | 0.183 | Fail to reject H0 |
| TEMP | two-sided | voice_rate_time | +10 | -0.179 | 0.032 | [-0.228, -0.128] | 1434/3246 | 9.57e-12 | 9.78e-11 | Reject H0 |
| HUM | two-sided | voice_rate_time | +10 | +0.083 | 0.007 | [+0.034, +0.132] | 1599/3245 | 0.000885 | 0.00973 | Reject H0 |

### OCCUPIED

| Air | Alt | Noise | Lag+min | r | r² | 95% CI | Neff/N | p_adj | q_BH | Decision |
|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| CO2 | greater | voice_rate_time | +10 | +0.157 | 0.025 | [+0.101, +0.213] | 1155/2710 | 3.76e-08 | 4.13e-07 | Reject H0 |
| dCO2_mean3 | greater | voice_rate_time | +2 | +0.188 | 0.035 | [+0.133, +0.242] | 1209/2635 | 2.15e-11 | 4.52e-10 | Reject H0 |
| PM25 | greater | voice_rate_time | +8 | +0.030 | 0.001 | [-0.039, +0.099] | 806/1609 | 0.196 | 0.413 | Fail to reject H0 |
| PM10 | greater | voice_rate_time | +8 | +0.031 | 0.001 | [-0.038, +0.100] | 807/1611 | 0.19 | 0.417 | Fail to reject H0 |
| TEMP | two-sided | voice_rate_time | +7 | -0.162 | 0.026 | [-0.219, -0.104] | 1110/2724 | 5.62e-08 | 1.32e-07 | Reject H0 |
| HUM | two-sided | voice_rate_time | +8 | +0.047 | 0.002 | [-0.011, +0.103] | 1179/2721 | 0.11 | 0.329 | Fail to reject H0 |

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
