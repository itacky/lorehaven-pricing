# CLAUDE.md: instructions for AI agents working in this repository

Read this file first. It says what the project is, the rules every agent follows, and where to find context.
Role-specific rules are in `.claude/agents/` (analyst, critic, tool-builder).

## Project in brief
Audible take-home, "Evaluating Lorehaven". Lorehaven is a simulated fantasy and sci-fi subscription that
launched at $15. It ran randomized $1-$5 discounts in every region except Panem, and cut the base price to
$12 in 2019 outside Panem. The brief asks:

1. Were the price changes effective?
2. What should membership pricing and discounts be going forward?

Deliverables:
- `writeup/writeup.pdf`: at most 2 pages and 3 visuals, with findings, a recommendation and an AI-use note.
- A pricing tool for a non-technical pricing lead (`app/`), with README, pinned environment, validation and
  tests.

Audience: the Audible Economics team. Status: complete. Later commits are refinements from Iman's own review and an external AI review.

**Current answer**, as quoted in the write-up and the tool. These are values from `metrics.json`; don't
restate them anywhere else:
- Discounts raise sign-up and retention, causally, because depth was randomized.
- The base cut is consistent with higher sign-ups, but not identified.
- Recommendation:
  - keep the $12 base;
  - make a $5 introductory offer the default, with a persistent randomized holdout (85% $5, 10% list, 5% $3);
  - tenure-based member discounts: $5 off the first two renewals, then $1;
  - win-back offers in a test arm only.

## Where the context lives

| File | What it is for | How to treat it |
|---|---|---|
| `PLAN.md` | The Phase 0 plan agreed with Iman: problem, success criteria, assumptions A1-A10, resolved open questions, phases | The baseline. Later decisions override it; check the decision log before relying on a detail (e.g. tested price ranges) |
| `FINDINGS.md` | Early exploration: data structure, data-quality issues, first estimates and strategy | **Claims to verify, not facts.** Re-derived in `outputs/results/findings_verification.csv` (42 of 46 match; 4 flagged) |
| `logs/decision_log.csv` | Every meaningful AI suggestion and what was done with it: `ts, phase, agent, suggestion, action (accept/edit/reject), reason` | Append-only. Read the recent rows for an area before changing it; add a row for each decision you make. Never rewrite history; append a correction |
| `logs/critic_phase2.md`, `logs/critic_phase4.md` | The two independent reviews and their triage | Settled issues; re-raise only with new evidence |
| `logs/SESSION_LOG.md` | Condensed history of the working session, with prompts marked verbatim or paraphrased | Narrative context: why things are the way they are |
| `outputs/results/metrics.json` | **Single source of truth** for every number (`value, unit, label, source, note`) | Read numbers from here; produce them only through `src/lorehaven/pipeline.py` |
| `prompts/` | The master prompt (verbatim) and the changelog of prompt and agent-definition versions | Add a changelog line when you change any agent definition or this file |
| `AI_WORKFLOW.md` | How AI was used, why three agents, what went wrong, how results were verified | Keep in step with the decision log |
| `README.md` | How to run the tool, the tests and the pipeline; key assumptions | Keep in step with what the scripts actually do |

## Shared rules (all agents)
1. **Never fabricate data or results.** Label everything `observed`, `estimate` or `assumption`. If a number
   is not in `metrics.json`, it is not reported.
2. **No hand-typed numbers downstream.**
   - The write-up uses `{{metrics.key|format}}` tokens (built by `writeup/build.py`).
   - The tool reads `metrics.json` (through `app/app.py`) or calls `simulate()`.
   - The notebook reads `metrics.json`.
   - To add a number, add it to the pipeline.
3. **Say what identifies every causal claim.** Randomized depth (A3) and as-good-as-random eligibility (A2)
   support causal claims. The base cut and pull-forward are descriptive. Write "consistent with", never "caused".
4. **Equations define every variable.** Use plain language for the pricing lead, and state units.
5. **Respect the tested ranges.** Results hold at the $12 base, for prospects at $7-$12 and members at
   $7-$11 (`simulator.tested_*`). Flag anything outside them as an extrapolation.
6. **Data hygiene.**
   - Raw data stays out of git (`data/raw/` is ignored).
   - No credentials or personal information in the repo.
   - Missing is missing: Westeros winter TV ratings, display impressions recorded as 0 despite spend, and
     display scores of exactly 0 are set to NaN.
7. **Verify before handing back.**
   - Run `python -m pytest -q` (all pass; one slow backcast test is opt-in).
   - Rebuild what you changed: `python -m lorehaven.pipeline --derived-only` for scenarios and headline
     numbers, or the full pipeline (needs the raw data and about 4 GB of RAM).
   - Run `python writeup/build.py` and check the PDF is still at most 2 pages.
   - For tool changes, open the tool in a browser.
8. **Small, readable code.** Self-explanatory names, a one-line docstring per function, an Inputs/Outputs
   note at the top of each `src/lorehaven` script. No notebook-only logic.
9. **Commits.** One commit per phase or change, with a message that says what and why. Log the decision in
   `logs/decision_log.csv` in the same commit.

## Agents and handoffs
The **main session** coordinates:
- it plans with Iman;
- it runs the analyst and tool-builder roles under their written rules (it already holds the context);
- it starts the critic as a separate fresh-context agent;
- it triages every critic issue into `logs/critic_phaseN.md` and the decision log;
- it commits.

| Agent | Produces | Hands off to |
|---|---|---|
| `analyst` | Code in `src/lorehaven/`, keys in `metrics.json`, result CSVs, and a run report | Main session (log, commit), critic (review), tool-builder (new keys) |
| `critic` (read-only) | A ranked issue table with evidence, plus a "Not checked" line | Main session, which triages each row as accept / edit / reject |
| `tool-builder` | `app/`, launchers, README, tests, and a handoff report with test counts and manual checks | Main session (log, commit; Iman tries it) |

Gates: high-severity critic issues are resolved before a phase is committed. Iman approves the plan, the
write-up wording and anything that changes the recommendation.

## Repo map
```
src/lorehaven/   data_prep -> models -> pipeline (writes metrics.json) ; simulate (the simulator) ; backcast ;
                 figures ; verify_findings
app/             Flask tool (Flask only at runtime): app.py, presets.py, templates/, static/
tests/           test_simulate.py, test_app.py, test_backcast.py
writeup/         writeup.md (tokens) -> build.py -> writeup.html / writeup.pdf
notebooks/       lorehaven_walkthrough.ipynb (presentation walkthrough); eda/ (early exploration scripts)
outputs/         results/ (metrics.json + CSVs), figures/ (3 PNGs)
run_tool.bat / run_tool.sh   one-step launchers (Windows / macOS-Linux)
```
