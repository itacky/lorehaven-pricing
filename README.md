# Lorehaven pricing analysis & simulator

Take-home for Audible Economics & Data Science. Status: **Phase 0 — scaffold** (see `PLAN.md`).
The tool, usage instructions and assumptions are completed in Phase 3.

## Data (not committed)
Place the three CSVs from the assignment in `data/raw/`:
```
data/raw/aggregate.csv
data/raw/customer_panel.csv
data/raw/customer_propensities.csv
```
`data/raw/` is gitignored. Nothing else needs to be downloaded.

## Setup
Python 3.10+ (tested on 3.10 and 3.13).
```
python -m venv .venv
.venv\Scripts\activate          # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

## Repository layout
| Path | Contents |
|---|---|
| `src/lorehaven/` | Data prep, models, `simulate()` |
| `app/` | Pricing tool (Phase 3) |
| `tests/` | Unit tests and backcast |
| `notebooks/eda/` | Prior exploratory analysis (reference only; claims re-verified in Phase 1) |
| `outputs/results/metrics.json` | Single source of truth for every reported number |
| `outputs/figures/` | Figures used in the write-up |
| `writeup/` | Write-up source and `writeup.pdf` |
| `FINDINGS.md` | Prior EDA findings (input to Phase 1 verification) |
| `PLAN.md` | Problem, success metrics, assumptions, open questions, phase plan |
| `prompts/`, `.claude/agents/`, `logs/decision_log.csv`, `AI_WORKFLOW.md` | AI workflow audit trail |
