# Architecture and design decisions

How the code fits together, and why each choice was made. Every decision lists the alternative considered and
what it costs, so it can be defended (or changed) on purpose.

## The flow

```
data/raw/*.csv
   │  data_prep.py      load with explicit types; derive status, tenure, base price, discount depth;
   ▼                    known data gaps set to missing
customer × quarter table (6.1M rows, 510k customers; cached as parquet)
   │  rates.py          group averages with counts: the evidence
   ▼
rate tables  ──────────────────────────────►  outputs/results/*.csv
   │  pipeline.py       records every number with a label
   ▼
outputs/results/metrics.json   ◄── single source of truth
   │                              │                          │
   │ projection.py (lookups)      │ figures.py               │ writeup/build.py
   │ recommendation.py            ▼                          ▼
   ▼                         outputs/figures/*.png      writeup.pdf
app/app.py (Flask) ── reads metrics.json, calls project()
```

`src/lorehaven/robustness/` is a side branch: it re-answers the same questions with regression models and writes
`outputs/robustness/`. Nothing in the main flow depends on it except one cross-check sentence in the write-up.

## Modules: one job each

| Module | Job | Depends on |
|---|---|---|
| `data_prep.py` | Raw CSVs → one tidy table | pandas |
| `rates.py` | The evidence: rates at each price by segment and tenure, with counts and errors | pandas |
| `projection.py` | Follow 1,000 prospects quarter by quarter by looking up rates | **standard library only** |
| `recommendation.py` | Named policies, first-quarter value, holdout size | projection |
| `pipeline.py` | Run the steps in order and record every number | all of the above |
| `figures.py` | The three write-up figures | metrics.json + CSVs |
| `app/app.py` | Web tool: form → `Policy` → `project()` → JSON | Flask + projection |

## Decisions

**1. Group averages, not regressions.**
*Why:* Lorehaven randomized who got an offer and how deep it was. With randomization, the average outcome of the
group that got $5 off minus the group that got no offer *is* the causal effect of $5 off. A regression adds
nothing to identification; it only smooths. Every cell has at least 556 customer-quarters, and every rate moves
the right way with price, so there is nothing to smooth.
*Alternative:* logit with region × quarter fixed effects (the first version). *Cost of the choice:* no single
"per $1" coefficient, and simple errors that ignore repeat customers. *Check:* `robustness/compare.py` answers 12
questions both ways; all agree in direction, sizes within 14%.

**2. Four prospect segments, three tenure groups.**
Prospects: engaged podcast listener (score ≥ 0.5) or not × never member or former member. Members: first renewal,
second renewal, third renewal on. *Why:* exploration showed podcast engagement is the one score that changes
price response, and former members behave differently from never-members. Tenure matters because new members
cancel far more often (Fig. 2). Three groups because renewals 3+ look alike. *Alternative:* more segments; each
extra split halves the cell sizes.

**3. One rate table per base-price era, never pooled.**
Lorehaven charged $15 (2017-18) and then $12 (2019), each with randomized $1-$5 discounts underneath, so each era
has its own causal table. *Why separate:* the same $12 drew different behaviour as a discount on $15 (10.1%
sign-up) and as the list price (6.0%); pooling eras would blend those. The recommendation and headline numbers use
the $12 table. *Cost:* comparing the $12 and $15 tables also compares 2019 with 2017-18, so a base-price comparison
is a direction, not a measured effect; the tool says so whenever the base is not $12.

**4. Look rates up; never fit a curve. Blend only between the two tested bases.**
*Why:* a lookup cannot extrapolate. The brief asks the tool to explore pricing as well as discount choices, so the
base price can be set from $12 to $15: $12 and $15 read their own table, and $13 and $14 blend them in a straight
line by discount (rate at $13 = two-thirds the $12 table + one-third the $15 table). Discounts: $0-$5 off for
prospects, $1-$5 off for members (every member had an offer, so full price for members was never seen).
*Alternatives:* (a) only $12 — no pricing choice at all, which the brief asks for; (b) a fitted price curve —
any base, but a model the main path does not otherwise need, and it would extrapolate. *Cost:* no "what if the base
were $10" answer; the honest answer to that is "run a test", which the recommendation says.

**5. A cohort projection, not just first-quarter numbers.**
*Why:* member discounts only pay off over several renewals, which a one-quarter view cannot show. The projection
is two lines of arithmetic per quarter: new members = prospects × sign-up rate at their price; members kept =
members × stay rate for their tenure and price. People are conserved (a test checks it). *Cost:* it assumes every
future quarter looks like an average 2019 quarter, so it ranks policies rather than forecasting.

**6. One file holds every number (`metrics.json`).**
*Why:* the write-up, figures and tool all read the same numbers, so they cannot disagree, and no number is typed
by hand. Each number is labelled observed, estimate or assumption. `--derived-only` re-runs projections without
the raw data. *Alternative:* each output computing its own numbers; that is how inconsistencies creep in.

**7. The tool needs only Flask.**
*Why:* a pricing lead should be able to run it with one double-click. `projection.py` uses only the standard
library and reads the rate tables from `metrics.json`, so pandas is not needed at runtime. The app holds no
analysis logic: it converts form inputs to a `Policy` and calls `project()`.

**8. Validation with plain messages, tied to a form field.**
*Why:* bad input should say what to fix, not return a server error. `InvalidPolicy` carries the field name, so the
page highlights the right box. NaN and infinity are rejected explicitly (they parse as floats).

**9. The holdout: 85% at $5, 10% at list, 5% at $3, assigned once per customer.**
*Why:* the full rollout gives up the randomization that made this analysis possible. *Sizing:* at about 268k
prospects a quarter, the 10% list arm detects a 0.5-point sign-up difference in one quarter (the real one is
19 points) and a 2-point renewal difference within three quarters (80% power, 5% significance). Renewal is the
open question, so 10% for the first quarters, 5% after. The $3 arm checks whether $5 is deeper than needed.

**10. The base cut is reported as direction only.**
*Why:* it was not randomized and Panem is the only comparison. Before the cut the gap to Panem moved between
-2.6 and -0.1 points with no price change, so a +3.1-point difference-in-differences cannot be called the effect.
The direction (below Panem every quarter before, above every quarter after) is robust.

**11. Keep the regression version as an appendix.**
*Why:* it is the answer to "did you consider a regression / IPW / a DiD model?": yes, and it agrees. It is
isolated in `robustness/` so the main flow can be read without it.

## Testing
- `test_rates.py`: hand-made tables where the right answer is obvious (e.g. 1 of 4 join → 25%).
- `test_projection.py`: invalid inputs, first quarter equals the table rates exactly, people are conserved,
  results scale with cohort size, deeper discounts move things the right way.
- `test_recommendation.py`: policies are valid, the value and power formulas are right.
- `test_app.py`: the page fills every number from metrics.json, presets run, bad input returns 400 with the field.
- `tests/robustness/`: the appendix's own tests.

## What I would do with more time
- Customer-clustered errors in the main tables (repeat customers make the simple errors a little too small).
- Seasonality in the projection (quarter-specific rates instead of the 2019 average).
- Run the holdout, then replace the "people respond the same at full coverage" assumption with its result.
