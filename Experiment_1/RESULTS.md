# Voice ↔ Air Quality — Summary (AIRQ001/002 × NOISE102)

**Window:** ALL → ALL • **TZ:** Europe/Madrid
**Minutes analysed (after quality filter):** AIRQ001 — ALL=3345, OCC=2804 • AIRQ002 — ALL=3345, OCC=2794
**Mean noise coverage:** 1.00 (ALL & OCC)

## Headline findings

* **CO₂ levels (ALL):** ✅ Voice activity **leads CO₂ by \~+10 min** in both kits.

  * AIRQ001: r=+0.114 @ +10 min, q=4.29e-05
  * AIRQ002: r=+0.121 @ +10 min, q=2.16e-05
* **ΔCO₂ (3-min mean) (ALL):** ✅ Peaks earlier (onset-sensitive).

  * AIRQ001: r=+0.172 @ +2 min, q=4.64e-11
  * AIRQ002: r=+0.156 @ +6 min, q=2.44e-09
* **Temperature (ALL):** ✅ Small **negative** association shortly after voice.

  * AIRQ001: r=−0.179 @ +10 min, q=9.78e-11
  * AIRQ002: r=−0.185 @ +2 min, q=3.25e-12
* **Humidity (ALL):** mixed/weak.

  * AIRQ001: small positive (r=+0.083 @ +10 min, q=0.0097)
  * AIRQ002: not significant
* **Particles PM₂.₅/PM₁₀ (ALL):** ❌ No FDR-significant associations in either kit.

**Occupied-minutes subset:** same story, slightly **stronger** magnitudes:

* CO₂: r≈+0.157…+0.168 @ +10 min (q≈10⁻⁷)
* ΔCO₂(3-min): r≈+0.155…+0.188 @ +2…+6 min (q≈10⁻⁷…10⁻¹⁰)
* TEMP: r≈−0.162…−0.191 @ +2…+7 min (q≈10⁻⁷…10⁻⁹)
* PM: not significant; HUM: not robust.

## Interpretation

* **Consistent, physical pattern:** people talk → **CO₂ rises a few–ten minutes later**; **temperature dips** shortly after (typical of ventilation/cooling when rooms are active).
* **Effect sizes:** modest (r≈0.11–0.19; r²≈1–4%), typical for minute-scale indoor data but statistically credible.

## Sanity check (reverse direction)

Negative-lag scans (Air → Noise) show **modest** peaks (max |r| ≤ \~0.19) consistent with shared transitions/edge effects; **forward** effects occur at physically expected lags and are at least as strong.

## Methods in brief

Pearson r over minute-aligned pairs with **Noise shifted forward** by candidate lags; **autocorrelation-aware** testing via effective sample size (N\_eff) and exact one-sided t-tests; **BH-FDR** across all forward lags per endpoint/scope (α=0.05); 95% CIs via Fisher z with N\_eff; reverse-lag scans reported (not included in FDR). Spearman ρ included in per-lag CSVs for robustness only.
