# Phase 4 — critic final review of the write-up and triage

Critic: fresh-context agent running `.claude/agents/critic.md`, read-only. It was given only its role, file
paths and the brief. Its tools were more limited than intended (Read only; no Grep or Glob), so it did not
re-review `data_prep.py` or `models.py`; the Phase 2 review covered those. A first run was stopped before it
returned a report and was re-run.

| # | Critic issue (abridged) | Sev. | Action | What changed |
|---|---|---|---|---|
| 1 | AI-use note still tagged DRAFT | high | accept | Tag removed; note kept in Iman's voice for his final read |
| 2 | "Revenue still rising at $5 in every segment" is false (former members peak at $4) | high | accept | Now: rising for never-members; former members peak at $4 |
| 3 | +133% assumes offers to 100% of prospects behave like the observed ~25% coverage | high | accept | Assumption stated in the Bottom line; the tool now warns when offer share exceeds the tested share (`simulator.tested_offer_share`); the holdout rollout is presented as how to test it |
| 4 | Limits quoted only the backcast baseline chosen after seeing results | high | accept | Both baselines reported, including the pre-planned one's 32% miss |
| 5 | Base cut stated as "raised sign-ups" despite failed pre-trend; first-quarter jump about 3× the randomized prediction | medium | accept | Now "consistent with higher sign-ups, not cleanly identified"; randomized-curve size (1.14 log-odds) given as best-identified |
| 6 | AI note claimed no hand-typed numbers; test counts inconsistent | medium | accept | Reworded (analysis numbers from metrics.json, process counts from logs/); test counts aligned (59 fast + 1 opt-in) |
| 7 | Causal label leans on eligibility assumption A2 without saying so | medium | accept | A2 stated in the Bottom line |
| 8 | Elasticity "rising with price" is by construction under a logit | low | accept | Stated as such |
| 9 | +133% depends on horizon | low | accept | Bottom line gives 3-year and 10-year figures |
| 10 | macOS/Linux quick start: `python` vs `python3`, pip --user blocked by PEP 668 | medium | accept | `run_tool.sh` creates a local .venv; README uses python3 for macOS/Linux |
| 11 | Pins have no Python 3.14 wheels | medium | accept | Python 3.10-3.13 stated (README, pyproject); tool-only `requirements-tool.txt` (Flask) |
| 12 | Fig. 1 title says "randomized" though the split relies on A2/A4; 0-100 axis | low | accept | Title fixed, assumption noted under the figure, axis 0-75 |
| 13 | Fig. 2 in-sample lines could read as validation | low | accept | Legend says the lines are fit to the same data |
| 14 | decision_log rows 39/40 double-count critic item #12 | low | accept | Correction row appended (history not rewritten) |
| 15 | Launcher and port edge cases; `member_value` possibly unused | low | edit | Port variable validated and fallback announced; Windows launcher checks Python version on every branch. `member_value` kept: the pipeline uses it for the steady-state comparison |
