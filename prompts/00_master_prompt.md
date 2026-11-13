# Master prompt (v1, 2026-11-12) — verbatim as given by Iman

I'm completing a data science take-home for Audible (attached: brief PDF, 3 CSVs, and my findings.md from prior exploratory analysis). The brief caps effort at a few hours and evaluates my AI workflow, so the process must be deliberate, small, and auditable. Right-sizing is part of the test.

DELIVERABLES (from the brief — these define "done")
1. writeup.pdf: ≤2 pages, ≤3 visuals, findings + pricing/discount recommendation + short AI-use note (how I used AI, where it fell short / what I corrected, how I verified)
2. Pricing simulation tool for a non-technical pricing lead: README (setup, usage, key assumptions), pinned environment, sensible structure, input validation with clear errors, tests
3. Everything in our local folder and eventually my Git repo. Raw data is or secrets are NOT committed: gitignore data/raw/ and document in the README where to place the CSVs. Commit history should be part of the audit trail: one commit per phase, with clear messages.

REPO STRUCTURE
README.md · pyproject.toml or requirements.txt (pinned) · data/raw/ (gitignored) · src/lorehaven/ (data prep, models, simulate) · app/ (tool) · tests/ · notebooks/ (analysis only) · outputs/results/metrics.json · outputs/figures/ · writeup/ (source + writeup.pdf) · prompts/ · logs/decision_log.csv · AI_WORKFLOW.md · .claude/agents/

AGENTS (.claude/agents/, short definitions)
- analyst: verifies findings.md, builds models and simulate(params), writes every number to outputs/results/metrics.json
- critic: read-only, fresh context; checks leakage, bad joins, post-treatment controls, missing data coded as zero, overclaimed causality, numbers not matching metrics.json, brief requirements missed; output format: issue | severity | evidence | fix
- tool-builder: packages simulate() into the tool (HTML, FLask, Streamlit or CLI) with README, tests, and input validation

RULES
- outputs/results/ is the single source of truth: no hard-coded numbers downstream
- Prompts versioned in prompts/ with a one-line changelog
- Log each accept/edit/reject of agent output to logs/decision_log.csv (ts, phase, agent, suggestion, action, reason)
- Never fabricate data or results; label assumptions vs. estimates
- No credentials or personal info in the repo
- Stop at each ✅ gate for my approval, then commit

* Keep it the implementation simple, keep the code simple, readable, modular and surgical. All code variables should be self intuitive open reading the variable names

DATA NOTES - customer_panel.csv is ~260MB: load with explicit dtypes and only the columns needed - Derive explicit columns: prospect/member status from the prior quarter, new sign-up (0→1), churn (1→0), base price, discount depth - Treat as missing, not zero: Westeros TV ratings in winter quarters, and display impressions in fall 2018 / spring 2019 / fall 2019 (spend > 0 in those quarters)

VERIFICATION (this is the eval) - findings.md: analyst re-derives each claim; mismatches are flagged, not silently fixed - simulate(): unit tests (edge cases, invalid inputs, monotonicity sanity checks) + backcast of 2017–2019 vs. actual member_count, with the error reported - critic cross-checks every number in the write-up against metrics.json

PHASES 0. Repo scaffold + agents; restate the problem, success metrics, assumptions, open questions, and a plan mapped to the deliverables ✅ 1. analyst → verify findings.md; fit acquisition and retention price-response models (quarter fixed effects, customer-clustered SEs, podcast ≥ 0.5 segment); DiD/event study for the $12 cut; incremental value + off-policy evaluation of targeting policies ✅ 2. critic review → fixes ✅ 3. tool-builder → tool + tests + backcast ✅ 4. write-up draft (I edit) → critic final review vs. the brief ✅ 5. AI_WORKFLOW.md: Mermaid diagram, agent roles and why only 3, decision-log summary, what AI got wrong, limitations Start with Phase 0. Stop after Phase 0.
