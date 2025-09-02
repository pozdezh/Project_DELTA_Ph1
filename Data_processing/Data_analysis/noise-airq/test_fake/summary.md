# Analysis Summary — AIRQ777 × NOISE777

_Window_: ALL → ALL  •  _Timezone_: Europe/Madrid
_Minutes analysed (after quality filter)_: ALL=240, OCCUPIED=234  •  Mean noise coverage: ALL=1.00, OCC=1.00

## Executive summary
- **Family-wise control:** BH-FDR across all tested lags per endpoint at α=0.05.
- **Interpretation rule:** For one-sided endpoints (CO₂, ΔCO₂, PM), the sign must match the alternative.

### Key endpoints (ALL minutes)
• **CO2:** ✗ best lag **+2 min**, r=+0.001 (95% CI [-0.524, +0.525]), r²=0.000, q=0.551, N_eff/N=14/232
• **dCO2_mean3:** ✓ best lag **+6 min**, r=+0.972 (95% CI [+0.929, +0.989]), r²=0.945, q=1.12e-11, N_eff/N=20/234
• **PM25:** ✗ best lag **+2 min**, r=+0.015 (95% CI [-0.120, +0.150]), r²=0.000, q=0.937, N_eff/N=212/232
• **PM10:** ✗ best lag **+0 min**, r=-0.052 (95% CI [-0.186, +0.085]), r²=0.003, q=0.971, N_eff/N=208/234
• **TEMP:** ✗ best lag **+8 min**, r=+0.139 (95% CI [-0.289, +0.520]), r²=0.019, q=0.673, N_eff/N=23/226
• **HUM:** ✗ best lag **+2 min**, r=+0.194 (95% CI [-0.121, +0.474]), r²=0.038, q=0.631, N_eff/N=41/232

### Key endpoints (OCCUPIED minutes)
• **CO2:** ✗ best lag **+0 min**, r=+0.041 (95% CI [-0.499, +0.557]), r²=0.002, q=0.505, N_eff/N=14/228
• **dCO2_mean3:** ✓ best lag **+6 min**, r=+0.974 (95% CI [+0.933, +0.990]), r²=0.949, q=1.39e-11, N_eff/N=19/228
• **PM25:** ✗ best lag **+2 min**, r=+0.006 (95% CI [-0.130, +0.142]), r²=0.000, q=0.945, N_eff/N=209/226
• **PM10:** ✗ best lag **+0 min**, r=-0.054 (95% CI [-0.191, +0.084]), r²=0.003, q=0.984, N_eff/N=203/228
• **TEMP:** ✗ best lag **+8 min**, r=+0.131 (95% CI [-0.301, +0.518]), r²=0.017, q=0.687, N_eff/N=23/220
• **HUM:** ✗ best lag **+1 min**, r=+0.191 (95% CI [-0.125, +0.472]), r²=0.036, q=0.666, N_eff/N=41/227

### Presence-controlled (OCCUPIED residuals)
_Slow presence (low-pass CO₂) and daily rhythm removed from both Voice and Air before lag scan._
• **CO2:** ✗ best lag **+9 min**, r=+0.304 (95% CI [-0.113, +0.631]), r²=0.093, q=0.287, N_eff/N=24/213
• **dCO2_mean3:** ✓ best lag **+6 min**, r=+0.909 (95% CI [+0.821, +0.955]), r²=0.826, q=3.89e-12, N_eff/N=33/216
• **PM25:** ✗ best lag **+2 min**, r=+0.081 (95% CI [-0.055, +0.214]), r²=0.007, q=0.558, N_eff/N=210/220
• **PM10:** ✗ best lag **+2 min**, r=-0.033 (95% CI [-0.175, +0.111]), r²=0.001, q=0.996, N_eff/N=187/220
• **TEMP:** ✗ best lag **+10 min**, r=-0.087 (95% CI [-0.353, +0.191]), r²=0.008, q=0.995, N_eff/N=52/212
• **HUM:** ✗ best lag **+0 min**, r=-0.182 (95% CI [-0.338, -0.017]), r²=0.033, q=0.343, N_eff/N=140/222

### Reverse-direction (negative-lag) diagnostics
_Air leading Noise (-10…-1 min); not part of FDR family._
**ALL:**
• **CO2:** reverse check max |r|=0.044 at lag -10 min (noise=voice_rate_time)
• **dCO2_mean3:** reverse check max |r|=0.197 at lag -1 min (noise=voice_rate_time)
• **PM25:** reverse check max |r|=0.102 at lag -8 min (noise=voice_rate_time)
• **PM10:** reverse check max |r|=0.129 at lag -7 min (noise=voice_rate_time)
• **TEMP:** reverse check max |r|=0.078 at lag -1 min (noise=voice_rate_time)
• **HUM:** reverse check max |r|=0.257 at lag -10 min (noise=voice_rate_time)

**OCCUPIED:**
• **CO2:** reverse check max |r|=0.043 at lag -1 min (noise=voice_rate_time)
• **dCO2_mean3:** reverse check max |r|=0.202 at lag -1 min (noise=voice_rate_time)
• **PM25:** reverse check max |r|=0.095 at lag -8 min (noise=voice_rate_time)
• **PM10:** reverse check max |r|=0.123 at lag -7 min (noise=voice_rate_time)
• **TEMP:** reverse check max |r|=0.076 at lag -1 min (noise=voice_rate_time)
• **HUM:** reverse check max |r|=0.272 at lag -10 min (noise=voice_rate_time)

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

## Methods (short)
- **Pearson r** on aligned minute pairs after shifting Noise forward by lag L.
- **Autocorrelation-aware testing:** estimate lag-1 autocorr for each series, derive an **effective N**, compute **t** and **p** with df = N_eff − 2.
- **One-sided tests** implemented directly from t and df.
- **FDR (BH)** across all forward lags per endpoint/scope → **q**; pick minimum-q lag (ties by p).
- **95% CI** for r via **Fisher z** using N_eff.
- **Reverse-direction** (negative lags) scanned and reported; excluded from FDR.
- **Quality**: minutes require `coverage_rate ≥ 0.50` and ≥1 frame; window gating occurs pre-analysis.
- **Occupancy proxy** parameters: base_quantile=0.1, base_add=50.0, dCO2_thresh=1.5.
- **Presence-controlled scope:** within OCCUPIED minutes, remove slow presence (low-pass CO₂, halflife 30 min) and daily rhythm (hour-of-day sine/cosine) from both Voice and Air, then re-run the same lag scan.
