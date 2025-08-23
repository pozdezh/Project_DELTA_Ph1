# Hypotheses Tested (`analysis_airq_noise.py`)

**Alpha:** `0.05`
**Lag windows:** levels `0–10` min; rates/diffs `0–20` min
**Notes:** Full-day tests use autocorrelation-adjusted p-values (effective N).
**Scopes:**

* **OCCWINDOW** = fixed local working hours + `occ_proxy == 1`
* **OCCDAILY** = auto-inferred work windows + `occ_proxy == 1`

---

## 1) Full-day association tests (`formal_hypothesis_tests`)

Best lag selected within the window; report uses one-sided/two-sided as specified.

* **CO₂ vs `voice_rate`** *(one-sided, greater)*

  * **H0:** ρ(voice\_rate, CO₂) ≤ 0
  * **H1:** ρ(voice\_rate, CO₂) > 0

* **ΔCO₂ vs `voice_rate`** *(one-sided, greater)*

  * **H0:** ρ(voice\_rate, ΔCO₂) ≤ 0
  * **H1:** ρ(voice\_rate, ΔCO₂) > 0

* **PM2.5 vs `voice_rate`** *(one-sided, greater)*

  * **H0:** ρ(voice\_rate, PM2.5) ≤ 0
  * **H1:** ρ(voice\_rate, PM2.5) > 0

* **TEMP vs `voice_rate`** *(two-sided)*

  * **H0:** ρ(voice\_rate, TEMP) = 0
  * **H1:** ρ(voice\_rate, TEMP) ≠ 0

* **HUM vs `voice_rate`** *(two-sided)*

  * **H0:** ρ(voice\_rate, HUM) = 0
  * **H1:** ρ(voice\_rate, HUM) ≠ 0

---

## 2) Occupied-window “increase” tests (`formal_increase_hypotheses_occwindow`)

Run on **OCCWINDOW** and (if enabled) **OCCDAILY**; one-sided (“greater”).

For each **a ∈ {CO₂, PM1, PM2.5, PM10, HUM, TEMP}**:

* **H0:** During/after speaking, *a* does not increase vs. silent presence (Δ ≤ 0)
* **H1:** During/after speaking, *a* increases vs. silent presence (Δ > 0)

Additionally, for **ΔCO₂**:

* **H0:** During/after speaking, the CO₂ change rate does not increase vs. silent presence (Δ ≤ 0)
* **H1:** During/after speaking, the CO₂ change rate increases vs. silent presence (Δ > 0)

> Implementation uses lagged Pearson with autocorrelation-adjusted p-values; best lag selected within the window.

---

## 3) Voice-vs-silent group comparisons

### 3a) Full dataset (no occupancy filter) — `voice_group_tests`

For each **a ∈ {CO₂, PM2.5, PM10, HUM, TEMP}**:

* **Welch t-test (two-sided)**

  * **H0:** μ₍voice=1₎(a) = μ₍voice=0₎(a)
  * **H1:** μ₍voice=1₎(a) ≠ μ₍voice=0₎(a)
* **Mann–Whitney U (two-sided)**

  * **H0:** Distributions of *a* are identical across groups
  * **H1:** Distributions of *a* differ across groups

### 3b) Within occupied periods (`occ_proxy == 1`) — `voice_group_tests_within_occupied`

Scopes: **ALL**, **VENT\_OFF**, **VENT\_ON**. For each **a ∈ {CO₂, PM2.5, PM10, HUM, TEMP, ΔCO₂}**:

* **Welch t-test (two-sided)**

  * **H0:** μ₍voice=1₎(a) = μ₍voice=0₎(a)
  * **H1:** μ₍voice=1₎(a) ≠ μ₍voice=0₎(a)
* **Reported one-sided (greater) view**

  * **H0:** μ₍voice=1₎(a) − μ₍voice=0₎(a) ≤ 0
  * **H1:** μ₍voice=1₎(a) − μ₍voice=0₎(a) > 0
* **HAC-robust OLS:** `a ~ voice_present` (one coefficient test)

  * **H0:** β\_voice = 0
  * **H1:** β\_voice > 0
    *(Two-sided HAC p-value also computed; summary prefers one-sided when discussing “increase”.)*

---

## 4) Exploratory (no formal H0/H1)

* **Cross-domain correlation heatmaps** (Pearson/Spearman) across all air × noise variables.
* **Lag scans** (levels and rolling/diffs) for selected pairs; report max |r| across lags for context.
