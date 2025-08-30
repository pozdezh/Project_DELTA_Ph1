# What the script does

* **Joins minute streams**: merges AirQ (`CO2`, `PM25`, `PM10`, `TEMP`, `HUM`) with Noise (`voice_rate_time`) by timestamp.
* **Quality gate**: keeps minutes with `coverage_rate ≥ 0.50` and ≥1 frame; optional time window via YAML.
* **Occupancy proxy**: flags OCCUPIED when CO₂ is above a low baseline or gently rising (3-min mean ΔCO₂ > threshold).
* **Lag scan**: tests if **Voice leads Air** by L minutes (L=0…10 for levels; 0…20 for ΔCO₂ mean), reports **Pearson r**, effective N (autocorr-adjusted), **alt-specific p**, **BH-FDR q**, and Fisher-z CIs.
  Reverse (negative) lags are listed as **diagnostics** only.
* **Presence-controlled scope**: within OCCUPIED, removes slow presence (low-pass CO₂, 30-min halflife) and daily rhythm (hour-of-day sin/cos) from **both** Voice and Air, then re-runs the lag scan. This isolates **short-term speech-linked effects**.
* **Outputs**: per-scope CSVs + a clean `summary.md` with decisions at α=0.05 (BH-FDR across forward lags per endpoint).

---

# Results + interpretation (considering HVAC & placement)

## Overall pattern (both kits vs NOISE102)

* **Short-term effect is on CO₂ rise, not level**: After presence control, **ΔCO₂ (3-min mean) stays significant at \~+4 min** for both kits
  (AIRQ001: r≈+0.096, q≈0.0028; AIRQ002: r≈+0.110, q≈0.00083).
  👉 Voice activity predicts a **small but robust** near-term increase in CO₂.
* **CO₂ level** (the absolute value) is significant in ALL/OCCUPIED but **vanishes after presence control** → that effect is mostly **baseline occupancy/diurnal** rather than an immediate response.
* **Particles (PM2.5/PM10)**: **no reliable association** after FDR in any scope.
* **Temperature**: Voice is **negatively** associated with TEMP at short lags (likely HVAC/opening windows during busy periods). After presence control:

  * AIRQ001: **not significant** (local HVAC/window effect minimal at that position).
  * AIRQ002: **weak but significant** cooling remains (r≈−0.091 at +10 min, q≈0.0079) → location matters.
* **Humidity**: Small, inconsistent effects. After presence control:

  * AIRQ001: tiny **positive** link remains (r≈+0.088, q≈0.019).
  * AIRQ002: **not significant**.

## By placement

### AIRQ001 — **centre of table cluster**

* **ΔCO₂** reacts **faster** in raw scopes (ALL/OCCUPIED best lag **+2 min**) and settles at **+4 min** after presence control.
  → Consistent with **local accumulation** in the seating cluster.
* **TEMP/HUM**: After presence control, TEMP **drops out** (no residual HVAC/window signal here); HUM shows a **very small** positive residual effect.

### AIRQ002 — **near window (sometimes open)**

* **ΔCO₂** appears **slower** in raw scopes (best lag **+6 min**), but aligns to **+4 min** after presence control.
  → The window likely causes **dilution/mixing**, delaying raw CO₂ rise; residual analysis reveals the same short-term speech effect.
* **TEMP** retains a **weak cooling** signal after presence control (−0.091 at +10 min), consistent with **window/HVAC influence** at this position.
* **HUM** doesn’t retain a robust residual link.

## Practical takeaway

* Report the **presence-controlled ΔCO₂ at \~+4 min** as the cleanest, location-agnostic indicator that **speech activity precedes near-term CO₂ increases**.
* Discuss **placement effects**: the near-window device shows HVAC/window signatures (cooling) and a slower raw ΔCO₂ lag due to dilution, whereas the centre device captures quicker accumulation.
* Particulate metrics show **no meaningful voice-linked changes** in this dataset.
