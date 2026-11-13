# Lorehaven Pricing — Findings & Reference (EDA → Strategy)

Reference for the final build (write-up + simulator). Every number below comes from a script in
`notebooks/eda/` and its output in `outputs/eda/`. Labels used throughout:

- **[Observed]** — a direct count or rate from the data
- **[Estimate]** — produced by a model; the model and its assumption are stated
- **[Assumption]** — something we chose or cannot verify from the data

Reproduce everything (≈2 min):
```
python notebooks/eda/prep.py <raw_dir> outputs/panel_prepared.parquet
python notebooks/eda/01_randomization_checks.py   outputs/panel_prepared.parquet outputs/eda
python notebooks/eda/02_price_response_by_propensity.py outputs/panel_prepared.parquet outputs/eda
python notebooks/eda/02b_thresholds.py            outputs/panel_prepared.parquet outputs/eda
python notebooks/eda/03_incrementality_segments.py outputs/panel_prepared.parquet outputs/eda
python notebooks/eda/04_price_points_elasticity.py outputs/panel_prepared.parquet outputs/eda
python notebooks/eda/05_strategy_checks.py        outputs/panel_prepared.parquet outputs/eda
```
`<raw_dir>` holds `customer_panel.csv` and `customer_propensities.csv`. Packages: pandas, numpy, scipy,
statsmodels, pyarrow.

---

## 0. Decisions agreed with Iman

| Topic | Decision |
|---|---|
| Primary metric | **LTV** = revenue per 1,000 prospects over a **12-season (3-year) horizon** |
| Secondary metrics | First-season revenue, members at end of horizon, ARPU (average revenue per member-season) |
| Guardrails | Churn per season; discount cost (revenue given up vs list); share of members discounted; extrapolation flag for prices outside $7–$15 |
| Discount rate on future revenue (d) | 0 by default, adjustable **[Assumption]** |
| Costs | **Content costs are out of scope.** Only the digital costs of the pricing strategy count. *Open: does "digital costs" mean discount cost only, digital marketing spend too, or both? Not yet answered — see §9.* |
| Tool | Lightweight static interactive HTML, no server; parameters exported from Python. UI inspiration: KPI tiles on top, white cards on light grey, one main line chart with hover tooltip, single accent colour (`color_guide_inspo`). |
| Customer segments | Podcast propensity cut at **0.5** (see §4) |
| Response labels | **Already Sold / Persuadable / Out of Reach** (shares of a segment, not labels on individuals) |
| Identification | **Randomized discount depth (and random offer eligibility) is the main analysis**; DiD on the 2019 base cut is the supporting check |

---

## 1. Data structure  [Observed]

| File | Grain | Rows | Notes |
|---|---|---|---|
| `customer_panel.csv` | customer × season | 6,121,068 = 510,089 × 12 | Balanced panel 2017–2019; no nulls; no duplicate keys; no customer ever changes `region_id` |
| `customer_propensities.csv` | customer × year (summer snapshot) | 1,530,267 | Join on `customer_id` + `year`; scores in [0, 1] |
| `aggregate.csv` | region × season | 72 | Spend is the same across regions each season (as the brief says) |

- There are 6 regions split into 20 sub-regions (`region_id`). Panem = sub-regions 6–11.
- `aggregate.csv` mostly duplicates the panel. `member_count`, `search_impressions`, `social_impressions`
  and `podcast_ad_listens` equal the panel sums exactly in all 72 rows. Only TV ratings, radio ratings and
  display impressions are new information.
- Season order is assumed to be winter → spring → summer → fall within each year **[Assumption]**. In the
  code, t = 0 is 2017 winter and t = 11 is 2019 fall.
- The .7z files were used only to transfer the CSVs. The extracted files match the CSVs byte for byte
  (260,649,403 and 168,416,062 bytes).

## 2. How prices and discounts were assigned  [Observed]

| Rule | Evidence |
|---|---|
| Base price is $15 everywhere until 2019 winter (t = 8). From 2019 spring (t = 9) it is **$12 in every non-Panem sub-region**; Panem stays at $15. | Checked sub-region by sub-region |
| Price paid = base − discount, and the discount is $1–$5 | 0 violations in 6.1M rows |
| **Members** (outside Panem) are offered a discount **100%** of the time | 100% in all 11 seasons |
| **Prospects** (never-members and lapsed members) are offered a discount **25%** of the time | 24.9%–25.5% in every season, region and status; not related to whether they were offered last season |
| Discount depth is **uniform across $1–$5** and re-drawn every season | 19.9%–20.1% at each depth; correlation with last season's depth = 0.0009 |
| Panem never gets a discount (members or prospects) | — |

**Correction to earlier EDA:** the overall discounted share rising from ~25% to ~49% was caused by members
becoming a larger share of the population. It was **not** a policy change. Prospect offer rates were flat
at 25% throughout.

### Randomization tests (`01`)  [Estimate]

| | Whether a prospect gets an offer (n = 3,346,845) | How deep the discount is (n = 1,425,154) |
|---|---|---|
| Largest covariate imbalance, standardized mean difference (SMD) | 0.003 | 0.005 |
| Joint F-test of all covariates (with sub-region + season dummies) | F = 0.79, p = 0.65 | F = 0.69, p = 0.75 |
| R² from covariates | 0.0000026 | 0.0000053 |
| How well the covariates predict assignment, AUC (0.5 = coin flip) | 0.502 | — |
| Offer rate by `customer_id` mod 2/3/4/5/10 | 24.9%–25.1% | — |
| Chi-square of depth vs sub-region / season / status / last season's depth | — | p = 0.89 / 0.65 / 0.47 / 0.21 |

SMD = (mean₁ − mean₀) / √((var₁ + var₀) / 2): the difference between groups in standard-deviation units.
Covariates tested: all 5 propensity scores plus a display-missing flag, last season's search / social /
podcast exposure, lapsed status, whether offered last season, and member tenure.

**[Assumption]** Eligibility is as good as random. The brief says business rules decide it, but no rule
shows up in any observable variable.

**Limitation:** treated-region members are discounted 100% of the time and Panem 0%, so there is no
within-region comparison of member retention at list price.

## 3. Data quality  [Observed]

| # | Issue | Evidence | Handling |
|---|---|---|---|
| 1 | Westeros TV ratings = 0 every winter | Spend is $56 / $87 / $141 in those seasons; other regions show 1M–15M ratings | Treat as missing; TV is not used in any model |
| 2 | Westeros search roughly halved every winter | `search_flag` 0.18 / 0.20 / 0.14 vs ~0.38–0.48 elsewhere; panel and aggregate agree. Sign-up rates are normal, so this leans toward a tracking gap — hypothesis only | Absorbed by region × season fixed effects |
| 3 | Display impressions = 0 in 2018 fall, 2019 spring and 2019 fall (all regions) | Display spend $8 / $7 / $14 | Treat as missing; not used |
| 4 | Display impressions are a whole number × region population | Identical per person across regions | Simulated field; not informative |
| 5 | Display propensity is mostly exact zeros, varying by year | Share exactly 0: 83% (2017), 0% (2018), 58% (2019); max 0.776 | Zeros treated as missing (`display_missing` flag) |
| 6 | Scores capped at exactly 1 | TV 13.8%, social 17.7%, radio 9.8%, podcast 9.9% | A ceiling, not an error |
| 7 | Radio and display score averages shift by year | Radio average 0.646 → 0.491 → 0.444; display average 0.009 / 0.335 / 0.031 | Any analysis by score must compare within year |

None of these touch the price, discount or sign-up fields.

## 4. Who responds to price (`02`, `02b`)  [Estimate]

Model in each subgroup (linear probability with fixed effects):

y = a(region, season) + b × price + e

- y = 1 if the customer signs up (prospects) or stays (members), otherwise 0
- a(region, season) = a separate baseline for each region × season
- b = change in probability per +$1, in percentage points (pp)

- **Podcast propensity is the dominant driver.** For prospects with score < ~0.41: sign-up 0.5–1%, slope
  about −0.9 pp/$. For score > ~0.54: sign-up ~13.7%, slope about −5.6 pp/$. The change between those
  levels happens over 0.41–0.54.
- The best single podcast cutoff (minimum residual sum of squares) is 0.525. **0.5 fits almost as well**
  (RSS difference 64, vs thousands for cutoffs ±0.1 away). 42% of prospects score ≥ 0.5.
- Social matters only at the low end: best cutoff 0.425, with 89% of prospects above it.
- TV has no effect. Radio and display have no effect once compared within year (their decile patterns
  came from the year mix — see §3, issue 7).
- **Retention:** 91% of members are high on both podcast and social. A retention cutoff search on podcast
  picked 0.375, but fewer than 2% of members fall below it — **not robust**.

## 5. Incrementality by prospect segment (`03`)  [Estimate]

Model in each segment: y = a(region, season) + Σₖ uplift(k) × 1[offer = $k off] + e.

- p0 = sign-up rate at list price (no offer) [Observed]
- uplift(k) = extra sign-up probability from a $k discount, vs list price

Decomposition at $5 off. This **assumes no one is put off by a discount** [Assumption]; 23 of 24 uplift
estimates are positive, and the one exception (−0.02pp) is noise.

- **Already Sold** = p0
- **Persuadable** = uplift(5)
- **Out of Reach** = 1 − p0 − uplift(5)

| Segment | Definition | Share of prospects | Already Sold | Persuadable ($5 off) | Out of Reach | Incremental share of discounted sign-ups |
|---|---|---|---|---|---|---|
| Win-backs | Former member, podcast ≥ 0.5 | 7.3% | 16.0% | 32.2% | 51.9% | 67% |
| Warm listeners | Never a member, podcast ≥ 0.5 | 34.9% | 7.8% | 27.1% | 65.1% | 78% |
| Lapsed, low-podcast | Former member, podcast < 0.5 | 0.8% | 5.4% | 16.4% | 78.2% | 75% |
| Cold | Never a member, podcast < 0.5 | 56.9% | 0.3% | 5.6% | 94.1% | 95% |

**Uplift grows faster than the discount (convex in price).** Across all prospects: +1.96pp at $1 off,
+7.34pp at $3, +15.15pp at $5, i.e. 1.96 / 2.45 / 3.03 pp per $ off. First-season discount $ per
incremental sign-up, computed as k × (p0 + uplift(k)) / uplift(k), is $3.08 at $1 off and $6.34 at $5 off
(first season only).

## 6. Price response (`04`)

### Observed rates by price, discounting regions  [Observed]

| Price | $7 | $8 | $9 | $10 | $11 | $12 | $13 | $14 | $15 |
|---|---|---|---|---|---|---|---|---|---|
| Sign-up, base $15 era | | | | 17.33% | 13.49% | 10.05% | 7.44% | 5.27% | 3.46% (list) |
| Sign-up, base $12 era | 25.22% | 20.42% | 15.72% | 12.07% | 8.39% | 5.98% (list) | | | |
| Retention, base $15 era | | | | 88.42% | 85.52% | 81.78% | 76.66% | 70.98% | |
| Retention, base $12 era | 94.94% | 93.74% | 92.21% | 90.41% | 87.86% | | | | |
| Panem members at $15 (reference, not randomized) | | | | | | | | | 69.62% |

### Logit model  [Estimate]

P(y = 1) = 1 / (1 + e^−(a(region, season) + β × price))

- a(region, season) = baseline log-odds for each region × season
- β = change in log-odds per +$1 of price

| | β per $ (standard error) | Odds multiplier per +$1, e^β |
|---|---|---|
| Sign-up | −0.3656 (0.0012) | 0.694 |
| Retention | −0.2787 (0.0028) | 0.757 |
| Sign-up, podcast < 0.5 / ≥ 0.5 | −0.606 / −0.400 | |
| Retention, podcast < 0.5 / ≥ 0.5 | −0.084 / −0.305 (only ~5% of members are < 0.5) | |

Fit: predicted and observed rates are within 0.7pp at every price point, except sign-up at $7, where the
model over-predicts (27.0% vs 25.2%).

Point elasticity: **E(p) = β × p × (1 − P(p))**, the % change in rate per 1% change in price.

- Sign-up: −1.87 (at $7) to −5.29 (at $15)
- Retention: −0.09 (at $7) to −1.10 (at $14)

### What elasticity means for value  [Estimate]

- **First-season revenue per prospect**, R = p × s(p), where s(p) is the sign-up probability:
  d ln R / d ln p = 1 + E_s, which is below 0 at every observed price. So **cutting price raises
  first-season revenue per prospect**.
- **Expected future revenue per member at a constant price**, V = p × r / (1 − r), where r is the
  per-season stay probability: d ln V / d ln p = 1 + E_r / (1 − r), which is below 0 at every observed
  price. Observed V values: $34 at $14 → $76 at $10 (base $15 era); $80 at $11 → $131 at $7
  (base $12 era).
- With the logit, the price that maximizes V is p* = −1/β ≈ **$3.59**. That is far below the tested
  range, so it is **extrapolation and must not be used as a recommendation**. The 12-season horizon in the
  simulator will be more conservative than this steady-state formula.

## 7. Strategy checks (`05`)  [Estimate]

**A. DiD on the 2019 base cut**, prospects at list price only. Treated-region no-offer prospects are a
random 75%, so they are comparable to Panem prospects. The model is a grouped logit with region and season
dummies:

- DiD effect δ = **0.829** (standard error 0.222) → odds ratio **2.29**
- The randomized curve predicts −3 × β = 1.097 → odds ratio 2.99. **Same direction and roughly the same
  size.**
- Placebo test (fake cut at t = 5, pre-period only): 0.138 (standard error 0.045). This is **not zero**,
  so parallel trends is shaky; treat the DiD size as approximate. There is only one control region, so the
  standard errors are optimistic.
- Raw list-price sign-up, before → after: treated 3.46% → 5.98%; Panem 4.92% → 4.12%.

**B. Do members react to price changes, not just price level?** Last season's price is random (depths are
re-drawn each season), so we can test it. Members, region × season fixed effects, excluding t = 9:

- Current price: −3.200 pp/$ (standard error 0.037)
- Last season's price: **−0.112 pp/$** (standard error 0.037). Small, and the opposite sign to "price
  increases cause extra churn".

**Members respond to the level of price, not to changes.** The random re-draws are not costing retention.

**C. First-season revenue per prospect** = (p0 + uplift(k)) × (base − k), $ per prospect:

| Segment | Era | List | $3 off | $4 off | $5 off |
|---|---|---|---|---|---|
| Warm listeners | base $15 | 1.01 | 2.42 | 2.92 | **3.32** |
| Warm listeners | base $12 | 1.64 | 2.84 | 3.03 | **3.13** |
| Win-backs | base $15 | 1.84 | 3.46 | 3.94 | **4.26** |
| Win-backs | base $12 | 2.53 | 3.89 | **3.96** | 3.90 |
| Cold | base $15 | 0.03 | 0.10 | 0.18 | **0.33** |
| Cold | base $12 | 0.06 | 0.47 | 0.71 | **0.91** |

## 8. Strategy (draft — to be confirmed by the 12-season simulator)

**Were the price changes effective?**
- **Discounts: yes.** They are randomized, so the effect is causal. 67–95% of discounted sign-ups are
  incremental, and every segment earns more first-season revenue with an offer than at list price.
- **The 2019 base cut: yes for acquisition.** List-price sign-up odds roughly 2.3× (DiD) to 3.0×
  (randomized curve). The exact size is uncertain because of the pre-trend.

**Prospects**
1. **Make the offer the default instead of a 25% lottery.** Every segment earns more at $5 off than at
   list, so the 75% not offered today is the biggest missed opportunity. Keep a randomized holdout
   (e.g. 10–20% at list, plus a few depth arms) so effects can keep being measured.
2. **Set depth by segment:**
   - Warm listeners and Cold: $5 off (the most tested). Revenue still rising at $5.
   - Win-backs: $4–$5 off. Revenue flattens and peaks at $4 in the $12 era. $4 gives up less on the
     16%+ who are Already Sold.
3. **Cold prospects (57%) are Out of Reach on price.** Offers to them are cheap (95% incremental) but add
   few members. Price is not the lever for this group.
4. **Test discounts below $7 in a small cell.** The value-maximizing price is below the tested range, so
   test it rather than extrapolate.

**Base price**
5. **Keep list at $12.** Don't cut list further on the model alone. Discounts can be targeted, are
   reversible, and keep generating test data; a list cut can't be undone easily.

**Members**
6. **Keep discounting members and move toward the deep end ($4–$5 off).** Retention elasticity is about
   −0.3 to −1.1, and V rises as price falls across the whole tested range. The 12-season LTV result must
   confirm this before it goes in the write-up as final, and ARPU must stay visible as a guardrail.
7. **Replace random re-draws with a stable member price.** Re-draws don't hurt retention (§7B), but once
   enough has been learned they add nothing. Keep a small randomized arm for continued learning.
8. **Panem (optional, flagged):** at $15 with no discounts, Panem members stay 69.6% of the time. A staged
   rollout of discounts there, with a holdout, would test whether the findings transfer. *Panem may be
   excluded for a business reason we don't know, so this is a suggestion, not a finding.*

**Guardrails to show next to every scenario:** ARPU, discount cost vs list, churn per season, share of
members discounted, and an extrapolation warning whenever a price is below $7.

## 9. Open items for the build

1. **Digital costs:** confirm whether this means discount cost only (current default), or digital
   marketing spend too.
2. **Simulator baseline:** decide which season(s) set the intercepts. Proposed: average of the treated
   regions over 2019 (t = 9–11), the current $12 regime. Anchors: list-price sign-up 5.98%; retention
   87.86% at $11 down to 94.94% at $7.
3. **Prospect pool dynamics:** prospects who don't join stay in the pool, and members who churn become
   lapsed (Win-backs follow different rates). Across the panel, 58.5% of customers never sign up.
4. **Seasonality:** the 2018 spring and 2019 summer shocks hit every region. The simulator should either
   use an average season or let users choose.
5. **Retention at full list price is not identified** inside the discounting regions. Flag any "members at
   list" scenario as extrapolation.
6. **Retention by podcast segment:** the β for podcast < 0.5 members (−0.084) is based on ~5% of members.
   Default to the pooled retention β unless a check supports splitting.

## 10. File index

| File | What it does |
|---|---|
| `notebooks/eda/prep.py` | Raw CSVs → one prepared table (customer × season) with derived fields |
| `notebooks/eda/01_randomization_checks.py` | Tests whether offer eligibility and discount depth are random |
| `notebooks/eda/02_price_response_by_propensity.py` | Price slopes by decile of each propensity score, plus joint model |
| `notebooks/eda/02b_thresholds.py` | Within-year check of radio/display; cutoff searches; podcast × social segments |
| `notebooks/eda/03_incrementality_segments.py` | Already Sold / Persuadable / Out of Reach by segment |
| `notebooks/eda/04_price_points_elasticity.py` | Rates by price point, arc elasticities, logit fits |
| `notebooks/eda/05_strategy_checks.py` | DiD on base cut, member price-change test, revenue per prospect |
| `outputs/eda/*.txt, *.csv` | Every number above (the prepared parquet file is not committed) |
