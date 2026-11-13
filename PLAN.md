# PLAN — Lorehaven pricing take-home (Phase 0)

## 1. Problem (restated)
Lorehaven is a stand-alone unlimited fantasy/sci-fi listening service. It launched at **$15**. Two changes
followed:

- **Discounts.** Offered in every region except Panem. A promotions engine decides who is eligible; the
  size of the discount is randomized.
- **Base price cut.** In 2019 the base price dropped to **$12** in most locations.

The brief asks two things:

1. **Were these price changes effective?**
2. **What should membership pricing and discounts be going forward?**

The answer has to be supported by the data and delivered as a write-up of at most two pages, plus a
simulator that a non-technical pricing lead can run.

## 2. What "done" means — success metrics for the deliverables

| Deliverable | Done when | Checked by |
|---|---|---|
| `writeup/writeup.pdf` | ≤ 2 pages; ≤ 3 visuals; contains findings, a pricing/discount recommendation (prospects and members), and an AI-use note; **every number traces to `metrics.json`** | Critic: 0 unresolved high-severity issues; 0 number mismatches |
| Pricing tool (`app/`) | Runs with one command after `pip install -r requirements.txt`; plain-language inputs and outputs; invalid inputs give a clear message; warns when a price is outside the tested $7–$15 range | Tests pass; manual run-through |
| Tests (`tests/`) | Edge cases, invalid inputs, monotonicity (lower price → not fewer sign-ups, not lower retention); backcast of 2017–2019 against actual `member_count` with the error written to `metrics.json` | `pytest` green |
| Verification of `FINDINGS.md` | Every numeric claim re-derived: match / mismatch table; mismatches flagged, not silently fixed | Analyst report + critic spot-check |
| Audit trail | One commit per phase; prompts versioned; every accept/edit/reject of agent output logged | Git log, `prompts/CHANGELOG.md`, `logs/decision_log.csv` |
| Hygiene | No raw data, credentials or personal info committed | `.gitignore`; critic check before each commit |

**Business metric used inside the analysis and tool** (agreed during EDA):

- **Primary: LTV.** Revenue per 1,000 prospects over a 12-season (3-year) horizon, at the price actually
  paid, so it is already net of discounts.
- **Secondary:** first-season revenue, members at the end of the horizon, and ARPU (average revenue per
  member-season).
- **Guardrails:** churn per season; discount cost (revenue given up vs list price — the only cost counted);
  share of members discounted; extrapolation warning when the effective price is below $7.

## 3. Assumptions (labelled; carried into the README and write-up)

| # | Assumption | Why / how we know | Type |
|---|---|---|---|
| A1 | Seasons run winter → spring → summer → fall within each year | No date field in the data | Assumption |
| A2 | Offer eligibility for prospects is as good as random | The brief says business rules decide it, but no observable predicts it (AUC 0.502, joint p = 0.65 in EDA; re-checked in Phase 1) | Assumption, supported by evidence |
| A3 | Discount depth ($1–$5) is randomized | Stated in the brief; balance tests pass in EDA | Stated in brief + verified |
| A4 | No one is less likely to join because they were offered a discount | Needed to split segments into Already Sold / Persuadable / Out of Reach; 23 of 24 uplift estimates in EDA are positive | Assumption |
| A5 | Price response follows a logit curve (log-odds linear in price) | Fits observed rates within 0.7pp except at $7 (over-predicts by 1.8pp) | Modelling choice |
| A6 | Estimates are valid only within the tested range: $7–$15 for prospects; $7–$14 for members, who were always discounted | Retention at full list price is not identified inside the discounting regions | Scope limit |
| A7 | Future revenue is not discounted (d = 0); adjustable in the tool | Agreed with Iman | Assumption |
| A8 | Only discount cost counts; content costs are out of scope | Agreed with Iman | Scope |
| A9 | Missing values are missing, not zero: Westeros winter TV ratings; display impressions in fall 2018 / spring 2019 / fall 2019; display propensity zeros | Spend is positive in those seasons | Data handling |
| A10 | Propensity scores are a summer snapshot each year, so winter and spring rows use a score measured later in the same year | How the data is built. Low leakage risk: the scores come from external data, and assignment does not depend on them (A2). The critic checks this. | Timing caveat |

## 4. Open questions — resolved by Iman (2026-11-12)
| # | Question | Decision |
|---|---|---|
| 1 | Tool form | **Flask**: one Python file serves an HTML page (styled after `color_guide_inspo`) that calls the Python `simulate()`. One copy of the model. `flask==3.1.0` pinned. |
| 2 | Fixed effects | **Region × quarter** is the main specification; quarter-only reported as a robustness check. |
| 3 | Backcast | **Both**: in-sample (fit 2017–2019) and out-of-sample (fit 2017–2018, predict 2019); both errors go to `metrics.json`. |
| 4 | Git | Commits made from this session, with deletion permission granted for the repo folder. Author: a GitHub no-reply address (no personal email in history). |
| 5 | Raw CSVs | Copied into `data/raw/` (gitignored, md5-verified identical) so the repo runs end to end; Iman's cloud copy remains the source of record. Code reads `LOREHAVEN_DATA_DIR` (default `data/raw/`). The tool runtime uses only exported parameters in `outputs/results/`. |
| 6 | Session log | Export the transcript at the end to `logs/session_transcript.md`, with personal details removed. |

## 5. Plan mapped to deliverables

| Phase | Agent | Work | Outputs | Verification | Feeds | Est. time |
|---|---|---|---|---|---|---|
| 0 ✅ | main | Scaffold, agents, this plan | Repo layout, `.claude/agents/`, `PLAN.md`, `prompts/`, `logs/` | Iman review | All | done |
| 1 ✅ | analyst | (a) Re-derive every `FINDINGS.md` claim → match/mismatch table. (b) Acquisition and retention logit models, region × quarter fixed effects, customer-clustered SEs, podcast ≥ 0.5 segment. (c) DiD + event study for the $12 cut, with a pre-trend test. (d) Incremental value by segment. (e) **Off-policy evaluation** of prospect targeting policies (see below). (f) `simulate(params)`. | `src/lorehaven/{data_prep,models,simulate}.py`, `outputs/results/metrics.json`, `outputs/results/findings_verification.csv` | Re-derivation table; identifying assumption stated next to every estimate | Write-up, tool | ~1.5 h |
| 2 ✅ | critic | Fresh-context review of Phase 1 | Issue table in `logs/critic_phase2.md` | Fixes logged as accept/edit/reject | — | ~0.5 h |
| 3 ✅ | tool-builder | Tool + README + validation + tests + backcast | `app/`, `tests/`, README completed | `pytest`; backcast error in `metrics.json` | Deliverable 2 | ~1 h |
| 4 ✅ | main → Iman → critic | Write-up draft (≤ 2 pages, ≤ 3 figures from `outputs/figures/`), Iman edits, critic final check against the brief and `metrics.json` | `writeup/writeup.md` → `writeup.pdf` | 0 number mismatches | Deliverable 1 | ~0.75 h |
| 5 ✅ | main | `AI_WORKFLOW.md`: Mermaid diagram, roles (why only 3), decision-log summary, what AI got wrong, limitations | `AI_WORKFLOW.md` | Iman review | AI note in write-up | ~0.25 h |

**Off-policy evaluation (Phase 1e).** The offers were assigned by a known random policy: P(offer) = 0.25
for prospects, then P($k off | offer) = 0.2 for each k. Because those probabilities are known, the value of
any alternative targeting policy π can be estimated by inverse propensity weighting:

V̂(π) = (1/n) Σᵢ yᵢ · 1[aᵢ = π(xᵢ)] / μ(aᵢ | xᵢ)

- aᵢ = the action prospect i actually received (no offer, or $1–$5 off)
- π(xᵢ) = the action policy π would give that prospect, based on their features xᵢ (segment)
- μ(aᵢ | xᵢ) = the logging probability of the action received: 0.75 for no offer, 0.25 × 0.2 = 0.05 for
  each depth
- yᵢ = the outcome (sign-up, or first-season revenue)

Policies to compare: no offers; status quo (random 25%); offer everyone $5; segment-targeted
(Warm $5 / Win-back $4 / Cold $5 or none).

**Limit:** this only works for prospects. Members always received a discount, so μ(list price | member) = 0
and no member policy that uses list price can be evaluated off-policy. Those scenarios rely on the model,
and the tool flags them.

## 6. Out of scope (right-sizing)
Media-mix / marketing attribution; content costs; individual-level uplift models; demand estimation
outside $7–$15; anything requiring data not provided.
