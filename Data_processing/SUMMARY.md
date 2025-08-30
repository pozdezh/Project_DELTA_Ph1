Imagine two clocks ticking through classroom time: one tracks **air** (CO₂, particles, temperature, humidity), the other tracks **sound activity** in the **voice band**. We want to know whether the gentle swell of voices is followed—minutes later—by a rise in CO₂, or a nudge in temperature, and so on. Not with guesses, but with careful, honest math.

### 1) Line up the minutes, and only keep the good ones

We join the Air and Noise timelines minute-by-minute, trim away outliers (the far 1% on both sides), and keep minutes with solid audio coverage. If we care about “people present,” we also build a simple **occupancy proxy**: “CO₂ above a low baseline” **or** “CO₂ rising a bit.” You can tune its knobs in the YAML file.

### 2) Slide one series past the other (the “lag” idea)

If **voices cause CO₂ to rise**, we should see the strongest alignment when **Noise is shifted a few minutes forward** (Noise leads, Air follows). We try a range of lags (e.g., +0 to +10 minutes for levels, +0 to +20 for ΔCO₂), and for each lag we compute **Pearson’s r**—a simple measure of linear association.

But real classroom data has memory: a busy room stays busy, CO₂ drifts up and down slowly. That “stickiness” inflates significance if we ignore it.

### 3) Be fair about “how much data we really have” (effective N)

So, for every test we estimate how autocorrelated each series is, and from that we compute an **effective sample size** $N_\text{eff}$. Then we compute a t-statistic and an exact **one-sided p-value** (for “CO₂ increases with voice”, for example) using **df = $N_\text{eff}$ − 2**. This keeps our confidence grounded.

We also compute a **Spearman** correlation as a friendly second opinion. It’s in the CSVs for each lag, but it doesn’t drive decisions.

### 4) If you look many places, control your excitement (FDR)

We’re scanning **many lags**—and, if you enable it, multiple noise proxies. To avoid chasing chance peaks, we collect **all** those forward-lag p-values for a given endpoint and scope and apply **Benjamini–Hochberg FDR**. Only after that do we pick “the best lag.” This is the family-wise honesty step.

### 5) Sanity check the other way around

We also look at **negative lags** (Air leading Noise). If our story is “voices → CO₂ shortly after,” we shouldn’t see equally strong peaks when we flip the direction. We **report** the largest negative-lag |r| as a quick plausibility check—yet we **don’t** mix these into the FDR family.

### 6) Report the result in human, not just numbers

The summary tells you, per scope (ALL/OCCUPIED):

* The **best lag**, the **correlation r**, and a 95% **confidence interval** built with $N_\text{eff}$.
* The **r²** (how much variance in Air is linearly explained—usually small but meaningful at scale).
* The **q-value** after FDR (our “guard against over-enthusiasm”).
* A compact **reverse-direction** note: did anything suspicious show up when we tested Air→Noise?

The tables are concise: one line per endpoint with the essentials. The per-lag CSVs contain the entire scan if you want to plot or dig deeper.

---

### What story typically emerges?

* **CO₂ & ΔCO₂**: small, consistent **positive** r’s at **+6–10 minutes**. People chat, then CO₂ creeps up—that’s exactly what you’d expect.
* **TEMP**: small **negative** r at short lags—often a sign of ventilation or cooling when the room is active.
* **PM**: usually **no strong link** at these time scales indoors, unless there’s a specific dust/aerosol source.
