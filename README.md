# Lorehaven pricing analysis & simulator

Take-home for Audible Economics & Data Science: were Lorehaven's price changes effective, and what should
membership pricing and discounts be? This repo holds the analysis (`src/lorehaven/`), every reported number
(`outputs/results/metrics.json`), and a small pricing simulator a non-technical pricing lead can run (`app/`).

## Quick start
Needs Python 3.10-3.13. The tool itself needs only Flask (`requirements-tool.txt`).

- **Windows:** double-click `run_tool.bat`. It finds Python (Anaconda, Miniconda or python.org), installs
  Flask if it is missing, starts the tool and opens it in your browser. Close the window to stop it.
- **macOS/Linux:** in Terminal, from this folder, run `bash run_tool.sh`. The first run creates a local `.venv`
  with Flask (about 20 s); later runs start immediately. Ctrl+C stops it. Open the address it prints if no
  browser window appears.

**How `run_tool.sh` finds Python (macOS/Linux).** It uses the first Python 3.10-3.13 it finds, in this order:
1. `LOREHAVEN_PYTHON`, if you set it;
2. the active conda environment (`CONDA_PREFIX`, i.e. after `conda activate ...`);
3. `python3.13` ... `python3.10`, `python3`, `python` on your PATH;
4. conda's base and environments, via `conda info --base` or `CONDA_EXE`;
5. the usual install folders: `~/anaconda3`, `~/opt/anaconda3`, `~/miniconda3`, `~/opt/miniconda3`,
   `~/miniforge3`, `~/mambaforge`, `/opt/anaconda3`, `/opt/miniconda3`, `/opt/miniforge3`,
   `/usr/local/anaconda3`, `/usr/local/miniconda3`, `/opt/homebrew/anaconda3`, Homebrew Caskroom
   Miniconda/Miniforge, Homebrew and python.org Pythons, and pyenv.

`bash run_tool.sh --which-python` prints the Python it would use, without starting anything.

**If it says "Could not find Python 3.10-3.13" (common with Anaconda on a Mac).** `bash run_tool.sh` does not
read `~/.zshrc`, where Anaconda adds itself to PATH, so it can land on Apple's built-in Python 3.9. Either:
```
conda activate base                                  # or your own environment, then:
bash run_tool.sh
```
or point the script at your Python directly:
```
conda activate base && which python                  # prints e.g. /Users/you/opt/anaconda3/bin/python
LOREHAVEN_PYTHON=/Users/you/opt/anaconda3/bin/python bash run_tool.sh
```
If your Anaconda base is older than Python 3.10, create an environment first:
`conda create -n lorehaven python=3.12`, then `conda activate lorehaven` and `bash run_tool.sh`.
Without the script: `python -m pip install flask==3.1.0` then `python app/app.py`, using any Python 3.10-3.13.

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

## Using the tool
The page reads top to bottom in the order of the brief:
1. **The answer.** Were the 2017-2019 price changes effective (discounts, the 2019 base cut, today's member
   discounts), next to the recommendation and its simulated value. *Load it in the simulator* applies it.
2. **The evidence.** Who a $5 offer wins (would-join-anyway vs persuadable), why member discounts belong at
   the first renewals, and what each policy earns over the chosen horizon.
3. **Test a policy.** The simulator. Set a policy in the **Simulator settings** panel on the right:
   - **Start from** a preset: *Recommended*, *Today's policy (2019)*, *Same $3 discount for all members*, or *No discounts*.
   - **Base price per quarter**: the list price. The model is calibrated at $12; any other base price is flagged.
   - **Introductory offer**: the share of prospects offered a discount and its size, set separately for
     *engaged listeners* (podcast-engagement score of 0.5 or more) and other prospects. *Former members get
     it too* switches win-back offers on or off.
   - **Member discounts**: the discount at the first two renewals, and from the third renewal on.
   - **More settings**: horizon (quarters), a discount rate on future revenue, and *random $1-$5 discounts*
     (today's promotions engine).

   Results update automatically: tiles (lifetime revenue, members at the end, first-quarter revenue, members
   leaving per quarter, each against today's policy), a members-per-quarter chart (hover for each quarter),
   guardrails, and an amber note whenever a setting goes outside what the data tested.
4. **Limitations.** What the numbers cannot tell you.

Every number on the page is read from `outputs/results/metrics.json` or computed by `simulate()`; none is typed
into the page. The *Recommended* preset is the full $5 rollout; the recommended rollout with its randomized
holdout (85% / 10% / 5%) is valued separately in `metrics.json` (`headline.holdout_design_*`), because the
simulator sets one offer per segment.

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
- **Behaviour.** Customers do not time cancellations or sign-ups around expected offers. The pull-forward check
  (`pull_forward.*` in metrics.json) is descriptive only: it conditions on prospects who did not join, so it
  cannot separate real timing shifts from who is left. A persistent holdout would measure it cleanly.
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
pytest                              # 74 fast tests: validation (incl. NaN/inf), edge cases, monotonicity, warnings, tool API, backcast errors
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
| `CLAUDE.md` (and `AGENTS.md`) | Instructions for AI agents: project overview, shared rules, where context lives, handoffs |
| `logs/SESSION_LOG.md` | Condensed session log: my prompts, what the AI did, what was corrected |
| `prompts/`, `.claude/agents/`, `logs/`, `AI_WORKFLOW.md` | AI-workflow audit trail |

## Extending
- **New preset**: add a dict to `app/presets.py` (form units: %, $, quarters).
- **New output**: add a KPI to `simulate()`'s `kpis` dict, then a tile or guardrail row in `app/static/app.js`.
- **New data or model**: change `models.simulator_fits`, re-run the pipeline, and the tool picks up the new
  parameters from metrics.json. Every value is labelled observed, estimate or assumption.
- **Styling**: `app/static/style.css` and `app/templates/index.html` hold layout and styling only. They can be
  changed without touching the model.
