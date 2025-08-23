# Noise ↔ Air Quality: Conclusions

### AIRQ001_NOISE102
- **CO₂ (occupied hours):** best lag **10 min**, r=0.074 (p=0.0028) → **Reject H0**.
- **ΔCO₂ (occupied):** best lag **5 min**, r=0.049 (p=0.0331) → **Reject H0**.
- **PM2.5 (occupied):** best lag **0 min**, r=-0.002 (p=0.5280) → **Fail to reject H0**.
- **PM10 (occupied):** best lag **0 min**, r=-0.003 (p=0.5351) → **Fail to reject H0**.
- **PM1 (occupied):** best lag **0 min**, r=-0.001 (p=0.5075) → **Fail to reject H0**.
- **TEMP (occupied):** best lag **9 min**, r=0.043 (p=0.0502) → **Fail to reject H0**.
- **HUM (occupied):** best lag **7 min**, r=0.055 (p=0.0191) → **Reject H0**.
- **CO₂ voice vs silent (OCCWINDOW:ALL):** Δmean = 105.55 (voice 1526.42 − silent 1420.88), one-sided p=0.1016 [HAC] → **Fail to reject H0**.
- **CO₂ voice vs silent (OCCWINDOW:VENT_OFF):** Δmean = 149.82 (voice 1530.78 − silent 1380.96), one-sided p=0.0508 [HAC] → **Fail to reject H0**.
- **CO₂ voice vs silent (OCCDAILY:ALL):** Δmean = 56.26 (voice 1593.19 − silent 1536.93), one-sided p=0.2508 [HAC] → **Fail to reject H0**.
- **CO₂ voice vs silent (OCCDAILY:VENT_OFF):** Δmean = 103.06 (voice 1607.00 − silent 1503.94), one-sided p=0.1334 [HAC] → **Fail to reject H0**.
- **Context (full-day CO₂ lag scan):** top |r| at **10 min**, r=0.134, N=3278.
- **Context (full-day ΔCO₂ lag scan):** top |r| at **5 min**, r=0.062, N=3226.
- **Top cross Pearson (|r|):** LLUM↔voice_score_mean (r=0.918); LLUM↔sfm_mean (r=-0.912); LLUM↔noiseRMS_mean (r=0.777); TEMP↔sfm_mean (r=0.772).
- **Top cross Spearman (|ρ|):** LLUM↔sfm_mean (ρ=-0.839); LLUM↔bandRMS_mean (ρ=0.834); LLUM↔snr_mean (ρ=0.829); LLUM↔noiseRMS_mean (ρ=0.824).

### AIRQ002_NOISE102
- **CO₂ (occupied hours):** best lag **10 min**, r=0.094 (p=0.0002) → **Reject H0**.
- **ΔCO₂ (occupied):** best lag **3 min**, r=0.076 (p=0.0024) → **Reject H0**.
- **PM2.5 (occupied):** best lag **0 min**, r=-0.002 (p=0.5207) → **Fail to reject H0**.
- **PM10 (occupied):** best lag **0 min**, r=-0.003 (p=0.5330) → **Fail to reject H0**.
- **PM1 (occupied):** best lag **0 min**, r=-0.003 (p=0.5291) → **Fail to reject H0**.
- **TEMP (occupied):** best lag **8 min**, r=0.012 (p=0.3232) → **Fail to reject H0**.
- **HUM (occupied):** best lag **9 min**, r=0.116 (p=5.1e-06) → **Reject H0**.
- **CO₂ voice vs silent (OCCWINDOW:ALL):** Δmean = 98.69 (voice 1537.94 − silent 1439.25), one-sided p=0.1230 [HAC] → **Fail to reject H0**.
- **CO₂ voice vs silent (OCCWINDOW:VENT_OFF):** Δmean = 141.67 (voice 1545.79 − silent 1404.12), one-sided p=0.0671 [HAC] → **Fail to reject H0**.
- **CO₂ voice vs silent (OCCDAILY:ALL):** Δmean = 61.27 (voice 1618.00 − silent 1556.73), one-sided p=0.2341 [HAC] → **Fail to reject H0**.
- **CO₂ voice vs silent (OCCDAILY:VENT_OFF):** Δmean = 105.33 (voice 1638.71 − silent 1533.38), one-sided p=0.1329 [HAC] → **Fail to reject H0**.
- **Context (full-day CO₂ lag scan):** top |r| at **10 min**, r=0.133, N=3277.
- **Context (full-day ΔCO₂ lag scan):** top |r| at **3 min**, r=0.088, N=3225.
- **Top cross Pearson (|r|):** TEMP↔sfm_mean (r=0.738); TEMP↔voice_score_mean (r=-0.718); TEMP↔noiseRMS_mean (r=-0.691); TEMP↔bandRMS_mean (r=-0.579).
- **Top cross Spearman (|ρ|):** LLUM↔noiseRMS_mean (ρ=0.816); LLUM↔bandRMS_mean (ρ=0.802); LLUM↔sfm_mean (ρ=-0.798); LLUM↔snr_mean (ρ=0.774).

### COMBINED
- **CO₂ (occupied hours):** best lag **10 min**, r=0.085 (p=2.1e-06) → **Reject H0**.
- **ΔCO₂ (occupied):** best lag **11 min**, r=0.022 (p=0.1176) → **Fail to reject H0**.
- **PM2.5 (occupied):** best lag **0 min**, r=-0.003 (p=0.5442) → **Fail to reject H0**.
- **PM10 (occupied):** best lag **0 min**, r=-0.003 (p=0.5494) → **Fail to reject H0**.
- **PM1 (occupied):** best lag **0 min**, r=-0.003 (p=0.5558) → **Fail to reject H0**.
- **TEMP (occupied):** best lag **3 min**, r=-0.000 (p=0.5030) → **Fail to reject H0**.
- **HUM (occupied):** best lag **8 min**, r=0.074 (p=3.0e-05) → **Reject H0**.
- **CO₂ voice vs silent (OCCWINDOW:ALL):** Δmean = 131.46 (voice 1539.84 − silent 1408.39), one-sided p=0.0201 [HAC] → **Reject H0**.
- **CO₂ voice vs silent (OCCWINDOW:VENT_OFF):** Δmean = 199.06 (voice 1570.97 − silent 1371.92), one-sided p=0.0040 [HAC] → **Reject H0**.
- **CO₂ voice vs silent (OCCDAILY:ALL):** Δmean = 71.59 (voice 1613.70 − silent 1542.11), one-sided p=0.1338 [HAC] → **Fail to reject H0**.
- **CO₂ voice vs silent (OCCDAILY:VENT_OFF):** Δmean = 145.72 (voice 1682.22 − silent 1536.50), one-sided p=0.0252 [HAC] → **Reject H0**.
- **Context (full-day CO₂ lag scan):** top |r| at **10 min**, r=0.129, N=6565.
- **Context (full-day ΔCO₂ lag scan):** top |r| at **11 min**, r=0.024, N=6449.
- **Top cross Pearson (|r|):** TEMP↔sfm_mean (r=0.752); TEMP↔voice_score_mean (r=-0.736); TEMP↔noiseRMS_mean (r=-0.688); TEMP↔bandRMS_mean (r=-0.575).
- **Top cross Spearman (|ρ|):** LLUM↔noiseRMS_mean (ρ=0.817); LLUM↔bandRMS_mean (ρ=0.816); LLUM↔sfm_mean (ρ=-0.814); LLUM↔snr_mean (ρ=0.800).
