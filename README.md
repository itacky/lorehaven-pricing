# Lorehaven pricing analysis & simulator

Take-home for Audible Economics & Data Science: were Lorehaven's price changes effective, and what should
membership pricing and discounts be? This repo holds the analysis (`src/lorehaven/`), every reported number
(`outputs/results/metrics.json`), and a small pricing simulator a non-technical pricing lead can run (`app/`).

## Quick start
Needs Python 3.10-3.13. The tool itself needs only Flask (`requirements-tool.txt`).

- **Windows:** double-click `run_tool.bat`. It finds Python (Anaconda, Miniconda or python.org), installs
  Flask if it is missing, starts the tool and opens it in your browser. Close the window to stop it.
- **macOS/Linux:** run `bash run_tool.sh`. The first run creates a local `.venv` with Flask (about 20 s);
  later runs start immediately. Ctrl+C stops it.

**Full environment (analysis, tests, notebook):**
Requires Python 3.10-3.13 (tested on 3.10 and 3.13).
```
python -m venv .venv                # macOS/Linux: python3 -m venv .venv
.venv\Scripts\activate              # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python app/app.py                   # prints the address (e.g. http://127.0.0.1:8050) and opens your browser
```
The tool needs no raw data: it reads the fitted parameters in `outputs/results/metrics.json`. To run *only*
the tool, Flask is the one package it needs (`pip install flask==3.1.0`). The tool picks a free local port
(8050 first; Windows often reserves 5000). To force one: `set LOREHAVEN_PORT=8765` (Windows) or
`LOREHAVEN_PORT=8765 python app/app.py` (macOS/Linux).

## Using the simulator
1. **Start from** a preset: *Recommended*, *Today's policy (2019)*, *Same $3 discount for all members*, or *No discounts*.
2. Change any setting. Results update automatically.
   - **Base price per quarter**: the list price. The model is calibrated at $12; any other base price is flagged.
   - **Offers to new customers**: the share of prospects offered a discount, and the size of that discount, set
     separately for *engaged listeners* (podcast-engagement score of 0.5 or more) and other prospects.
     *Former members also get the offer* switches win-back offers on or off.
   - **Current members**: the discount at the first two renewals, and the discount from the third renewal on.
   - **More settings**: horizon (quarters), a discount rate on future revenue, and *random $1-$5 discounts*
     (today's promotions engine).
3. Read the results.
   - **Top tiles**: revenue per 1,000 prospects over the horizon (lifetime value), members at the end,
     first-quarter revenue, and members leaving per quarter. Each shows its change against today's policy.
   - **Chart**: members per quarter for your policy against today's. Hover to see each quarter.
   - **Guardrails**: average revenue per member, discounts given away, share of member-quarters paying a
     discounted price, and churn. An amber note appears whenever a setting goes outside what the data tested.

Invalid settings (for example a discount above the base price, or an offer share over 100%) are refused with
a message saying what to change, and the box concerned is highlighted.

## Key assumptions
Each assumption is listed in `PLAN.md` §3 and labelled in `metrics.json` (`label`: observed / estimate / assumption).
- **Causal price effects come from Lorehaven's own randomization.** Discount depth ($1-$5) is randomized by
  design. Whether a prospect is offered a discount looks random on everything observable; we treat it as
  random (assumption A2).
- **Simulator calibration.** Curves are fit on the discounting regions in 2019 spring-fall (the $12 regime),
  separately for engaged and other prospects, for never-members and former members, and for members at
  their first renewal, second renewal and later. Every quarter is treated as an average 2019 quarter: no
  seasonality and no marketing changes.
- **Tested range.** New-customer prices are tested from `simulator.tested_prospect_price_min` to `_max`, and
  member prices from `simulator.tested_member_price_min` to `_max`. Members paying full price were never
  observed. Anything outside these ranges is flagged as an extrapolation.
- **Revenue** is what members actually pay, so it is already net of discounts. The only cost counted is the
  discount itself. Content costs are out of scope.
- **Behaviour.** Customers do not time cancellations or sign-ups around expected offers. Measured pull-forward
  is small (`pull_forward.*` in metrics.json).
- **Accuracy.** The backcast fits on 2017-2018 and predicts 2019 (`backcast.*`). It is close in the
  discounting regions and poor in Panem. Use the tool to compare policies, not to forecast member counts.

## Reproduce the analysis
Place the three CSVs from the assignment in `data/raw/`, or set `LOREHAVEN_DATA_DIR` to their folder:
```
data/raw/aggregate.csv
data/raw/customer_panel.csv
data/raw/customer_propensities.csv
```
`data/raw/` is gitignored. For the analysis commands, first run `pip install -e .` (it makes
`python -m lorehaven...` work from any folder). Re-running the analysis needs about 6 GB of free memory. The tool and the
default tests need very little.
```
python -m lorehaven.pipeline        # about 1 minute: models, scenarios, backcast, metrics.json, FINDINGS.md verification
pytest                              # 59 fast tests: validation, edge cases, monotonicity, warnings, tool API, backcast errors
LOREHAVEN_RUN_SLOW=1 pytest         # adds a full backcast re-run from the raw CSVs (~4-5 GB RAM)
```
Outputs are written to `outputs/results/`:

| File | Contents |
|---|---|
| `metrics.json` | Every reported number, each with unit, label and source |
| `findings_verification.csv` | Every FINDINGS.md claim re-derived: match or MISMATCH |
| `rates_by_price.csv` | Observed sign-up and retention rates by price |
| `prospect_discount_efficiency.csv` | Prospect response by segment and depth |
| `member_discount_efficiency.csv` | Member response by segment and price |
| `uplift_by_segment_*.csv` | Uplift by segment, all eras and $12 era |
| `off_policy_evaluation.csv` | Off-policy policy values |
| `event_study.csv`, `base_cut_observed.csv` | 2019 base cut |
| `model_fit_check_in_sample.csv` | In-sample fit |
| `backcast.csv` | Backcast by region and quarter |

## Repository layout
| Path | Contents |
|---|---|
| `src/lorehaven/data_prep.py` | Loads CSVs with explicit dtypes; derives status, sign-up, churn, base price, discount depth and tenure; known data gaps are stored as missing values |
| `src/lorehaven/models.py` | Fixed-effect logits with clustered SEs, per-segment fits, DiD and event study, uplift, discount efficiency, off-policy evaluation, simulator fits |
| `src/lorehaven/simulate.py` | `simulate(policy, model)`, input validation, extrapolation warnings |
| `src/lorehaven/backcast.py` | Replays 2017-2019 with the simulator's quarter step |
| `src/lorehaven/pipeline.py`, `verify_findings.py` | Writes metrics.json; re-derives FINDINGS.md claims |
| `app/` | Flask tool. `app.py` (routes), `presets.py`, `templates/`, `static/` (layout and styling only) |
| `tests/` | pytest suite |
| `notebooks/lorehaven_walkthrough.ipynb` | Presentation walkthrough of the EDA, calculations, models and checks (executed; readable on GitHub) |
| `notebooks/eda/`, `outputs/eda/` | Earlier exploratory analysis (reference; verified in Phase 1) |
| `writeup/` | Write-up source and PDF |
| `PLAN.md`, `FINDINGS.md` | Plan and assumptions; earlier EDA findings |
| `prompts/`, `.claude/agents/`, `logs/`, `AI_WORKFLOW.md` | AI-workflow audit trail |

## Extending
- **New preset**: add a dict to `app/presets.py` (form units: %, $, quarters).
- **New output**: add a KPI to `simulate()`'s `kpis` dict, then a tile or guardrail row in `app/static/app.js`.
- **New data or model**: change `models.simulator_fits`, re-run the pipeline, and the tool picks up the new
  parameters from metrics.json. Every value is labelled observed, estimate or assumption.
- **Styling**: `app/static/style.css` and `app/templates/index.html` hold layout and styling only. They can be
  changed without touching the model.
