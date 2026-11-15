# Lorehaven pricing analysis & simulator

Take-home for Audible Economics, Research & Optimization (AERO): were Lorehaven's price changes effective, and what should
membership pricing and discounts be? This repo holds the analysis (`src/lorehaven/`), every reported number
(`outputs/results/metrics.json`), and a small pricing simulator a non-technical pricing lead can run (`app/`).

**The method in one line:** Lorehaven randomized its discounts, so the analysis compares group averages (sign-up and
stay rates at each price) and projects policies by looking those rates up quarter by quarter. No fitted models are
needed; a model-based version is kept in `src/lorehaven/robustness/` as a cross-check. Design decisions and the
reasons for them are in [`ARCHITECTURE.md`](ARCHITECTURE.md).

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
The tool needs no raw data: it reads the observed rate tables in `outputs/results/metrics.json`. To run *only*
the tool, Flask is the one package it needs (`pip install flask==3.1.0`). The tool picks a free local port
(8050 first; Windows often reserves 5000). To force one: `set LOREHAVEN_PORT=8765` (Windows) or
`LOREHAVEN_PORT=8765 python app/app.py` (macOS/Linux).

## Using the tool
The page reads top to bottom in the order of the brief:
1. **The answer.** A scorecard for the 2017-2019 changes: a verdict on each (discounts, the 2019 base cut,
   today's member discounts), how strong the evidence is, and the key number. Below it, the four-step
   recommendation and its projected value. *Load it in the simulator* applies it.
2. **The evidence, in three numbers.** Click a number to see its detail: who a $5 offer wins (would-join-anyway
   vs persuadable, by segment), renewal for new vs established members, and what each policy earns over the
   chosen horizon.
3. **Test a policy.** Set a policy in the **Policy settings** panel on the right:
   - **Start from** a preset: *Recommended*, *Today's policy (2019)*, *Same $2 discount for all members*, or
     *No intro offer, $1 off for members*, *Recommended discounts at the old $15 base*.
   - **Base price per quarter**: $12-$15. Lorehaven charged $15 (2017-18) and $12 (2019); $13 and $14 blend the
     two eras' rates. A note appears whenever the base is not $12, because the eras differ in more than price.
   - **Introductory offer**: the share of prospects offered a discount and its size ($0-$5), set separately for
     *engaged listeners* (podcast-engagement score of 0.5 or more) and other prospects. *Former members get
     it too* switches win-back offers on or off.
   - **Member discounts**: $1-$5 off at the first two renewals, and from the third renewal on.
   - **More settings**: horizon (quarters), a discount rate on future revenue, and *random $1-$5 discounts*
     (today's promotions engine).

   Only tested prices can be chosen, because the projection reads observed rates and has nothing to say about
   prices that were never tried. Results update automatically: tiles (revenue,
   members at the end, first-quarter revenue, members leaving per quarter, each against today's policy), a
   members-per-quarter chart (hover for each quarter), guardrails, and an amber note when offers reach more
   prospects than the 25% the data saw or the base is not $12.
4. **Limitations.** What the numbers cannot tell you.

Every number on the page is read from `outputs/results/metrics.json` or computed by `project()`; none is typed
into the page. The *Recommended* preset is the full $5 rollout; the recommended rollout with its randomized
holdout (85% / 10% / 5%) is valued separately in `metrics.json` (`headline.rollout_*`), because the tool sets one
offer per segment.

Invalid settings (a discount that was never tested, an offer share over 100%, a fractional horizon) are refused
with a message saying what to change, and the box concerned is highlighted.

## Key assumptions
Each assumption is listed in `PLAN.md` §3 and labelled in `metrics.json` (`label`: observed / estimate / assumption).
- **Causal price effects come from Lorehaven's own randomization.** Discount depth ($1-$5) is randomized by
  design. Whether a prospect is offered a discount looks random on everything observable; we treat it as
  random (assumption A2). That is why a difference of group averages is the effect of price.
- **The projection uses observed rates from each base-price era.** Sign-up and stay rates come from the
  discounting regions, by engagement segment, by never vs former member, and for members at their first
  renewal, second renewal and later: 2019 spring-fall for the $12 base (the recommendation) and 2017-18 for the
  $15 base. $13 and $14 are a straight-line blend. Comparing bases also compares years, so it is a direction only. Every quarter is treated as an average 2019 quarter: no seasonality and no
  marketing changes. Use it to rank policies, not to forecast member counts.
- **Tested prices only.** A $12-$15 base, $0-$5 off for prospects and $1-$5 off for members. Members paying full
  price were never observed, so the tool does not allow it.
- **Revenue** is what members actually pay, so it is already net of discounts. The only cost counted is the
  discount itself. Content costs are out of scope.
- **Behaviour.** Customers do not time cancellations or sign-ups around expected offers. This cannot be checked
  in the data; the persistent holdout would measure it.
- **Errors.** Standard errors treat customer-quarters as independent. Customers repeat across quarters, so
  true errors are somewhat larger; the appendix reports customer-clustered errors.

## Reproduce the analysis
Place the three CSVs from the assignment in `data/raw/`, or set `LOREHAVEN_DATA_DIR` to their folder:
```
data/raw/aggregate.csv
data/raw/customer_panel.csv
data/raw/customer_propensities.csv
```
`data/raw/` is gitignored. For the analysis commands, first run `pip install -e .` (it makes
`python -m lorehaven...` work from any folder). Re-running the analysis needs about 6 GB of free memory. The tool and the
tests need very little.
```
python -m lorehaven.pipeline        # about 30 s: rate tables, projections, metrics.json
python -m lorehaven.figures         # the three write-up figures
python writeup/build.py             # write-up HTML and PDF (needs Chrome or Edge)
pytest                              # fast tests: rate tables on synthetic data, projection accounting, tool API
python -m lorehaven.robustness      # OPTIONAL appendix, about 1-2 min: model-based cross-check (needs statsmodels)
```
Main outputs, in `outputs/results/`:

| File | Contents |
|---|---|
| `metrics.json` | Every reported number, each with unit, label (observed / estimate / assumption) and a note |
| `signup_by_price.csv`, `stay_by_price.csv` | Sign-up and stay rates at every price, both base-price eras |
| `signup_by_segment_and_discount.csv` | Sign-up by segment and discount, uplift and share the offer won, for each base-price era ($12, $15) |
| `stay_by_tenure_and_price.csv` | Stay rate by engagement, tenure and price, for each base-price era (the projection's member tables) |
| `base_cut_two_by_two.csv`, `base_cut_gap_by_quarter.csv` | 2019 base cut vs Panem |

Appendix outputs, in `outputs/robustness/`: the model-based `metrics.json`, `simple_vs_advanced.csv` (the same
questions answered both ways) and `crosscheck.json` (the summary quoted in the write-up).

## Repository layout
| Path | Contents |
|---|---|
| `src/lorehaven/data_prep.py` | Loads CSVs with explicit dtypes; derives status, sign-up, churn, base price, discount depth and tenure; known data gaps are stored as missing values |
| `src/lorehaven/rates.py` | The evidence: sign-up and stay rates as group averages with counts, by price, segment and tenure; the base-cut comparison |
| `src/lorehaven/projection.py` | `project(policy, rates)`: follows 1,000 prospects quarter by quarter by looking up the observed rates; input validation |
| `src/lorehaven/recommendation.py` | Named policies, first-quarter value, holdout sizes (minimum detectable difference) |
| `src/lorehaven/pipeline.py` | Runs the steps above and writes metrics.json |
| `src/lorehaven/figures.py`, `formatting.py` | Write-up figures; display rounding |
| `src/lorehaven/robustness/` | APPENDIX: fixed-effect logits, inverse-propensity weighting, logit DiD, fitted-curve simulator, backtest, and `compare.py` |
| `app/` | Flask tool. `app.py` (routes), `presets.py`, `templates/`, `static/` (layout and styling only) |
| `tests/` | pytest suite (`tests/robustness/` for the appendix) |
| `notebooks/lorehaven_walkthrough.ipynb` | Short walkthrough of the simple analysis (executed; readable on GitHub) |
| `notebooks/appendix/`, `notebooks/eda/`, `outputs/eda/` | Earlier model-based walkthrough and exploratory analysis (reference) |
| `writeup/` | Write-up source and PDF |
| `ARCHITECTURE.md` | How the code fits together and why each design decision was made |
| `PLAN.md`, `FINDINGS.md` | Plan and assumptions; earlier EDA findings |
| `CLAUDE.md` (and `AGENTS.md`) | Instructions for AI agents: project overview, shared rules, where context lives, handoffs |
| `logs/SESSION_LOG.md` | Condensed session log: my prompts, what the AI did, what was corrected |
| `prompts/`, `.claude/agents/`, `logs/`, `AI_WORKFLOW.md` | AI-workflow audit trail |

## Extending
- **New preset**: add a dict to `app/presets.py` (form units: %, whole $, quarters).
- **New output**: add it to the `summary` dict in `projection.project()`, then a tile or guardrail row in `app/static/app.js`.
- **New data**: re-run the pipeline; the tool reads the new rate tables from metrics.json.
- **A price that was never tested** (another base price, members at full price): run a randomized test first, add
  its rates to the tables, then widen the allowed range in `projection.validate()`.
- **Styling**: `app/static/style.css` and `app/templates/index.html` hold layout and styling only.
