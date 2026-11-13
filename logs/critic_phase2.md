# Phase 2 — critic review and triage

Critic: fresh-context general-purpose agent running `.claude/agents/critic.md` (read-only: Read/Grep/Glob),
given only its role, file paths and the brief. It reviewed commit `e869ee3` (Phase 1).
Its raw output is summarised below (issue | severity | fix requested), followed by the action taken.
Every row is also in `logs/decision_log.csv`.

| # | Critic issue (abridged) | Sev. | Action | What changed / evidence |
|---|---|---|---|---|
| 1 | Extrapolation warnings used $7-$15 / $7-$14, but simulator curves are fit on q9-q11 where prospects saw $7-$12 and members $7-$11 | high | accept | Tested ranges now come from the fit sample and are stored in metrics.json (`simulator.tested_*`); warnings for member price >= base and for any base price other than $12 |
| 2 | "Deeper member discounts lower LTV" rests on the unobserved $12 member price and the 12-quarter horizon | high | accept | Scenarios reported at 12/20/40 quarters; member-at-list scenarios carry warnings. With tenure added (#9) the answer became: deep discounts for new members, shallow for established |
| 3 | "A price is a price": same price gives different outcomes as discount vs list ($12: 10.05% as $3 off $15 vs 5.98% list) | high | accept | Not separable within an era (confounded with time). Simulator restricted to the $12 base it was fit on; base-price changes flagged as extrapolation; no base-vs-discount ranking claimed |
| 4 | Base-$15 counterfactual is an out-of-sample extrapolation (misses $15-era retention by up to ~10pp) | high | accept | `status_quo_base15` scenario removed; base cut evaluated on observed data instead (#13) |
| 5 | DiD: pre-trend fails, customer-clustered SE far too small, single delta hides decay | high | accept | SE clustered by sub-region (20 clusters); event-study path reported; DiD labelled direction-only, no effect size claimed |
| 6 | Pull-forward not modelled | high | edit | Tested: deeper offer now lowers next-quarter sign-up by 0.14pp per $ (high podcast) vs +5.3pp immediate (~3% offset); low podcast ~1%. Recorded (`pull_forward.*`) and stated as a caveat; not added to the simulator (small) |
| 7 | Segment results pool eras; Cold "out of reach" contradicted by the $12 era | high | accept | `uplift.base12.*` is primary: Cold at $5 off gains +12.4pp (96% incremental). Cold recommendation rewritten |
| 8 | High-podcast share computed over all customers incl. members | high | accept | Now share among never-member prospects (q9-q11): 24.3% (was 48.7%) |
| 9 | Retention ignores tenure; churn-and-rejoin loop | medium | accept (raised to high) | Checked: first-renewal retention 88.7% vs ~95% established (high podcast); 55.5% vs ~95% (low). Simulator now tracks first renewal / second renewal / established. Rejoin rate does NOT decay with time since lapse (19.8-22.1%), so the lapsed-stock rate is kept |
| 10 | Summer propensity score may be post-treatment | medium | reject (with evidence) | A randomized winter or spring offer does not move the same-year summer podcast score (e.g. 2019 winter: 0.4814 vs 0.4820) |
| 11 | Same estimand from different samples (pipeline vs verification) | medium | accept | One documented analysis sample in pipeline.py; verification values written under `verification.claimNN` keys; write-up quotes pipeline keys only |
| 12 | OPE myopic, pools eras, targeting chosen post hoc | medium | edit | Restricted to the $12 regime with SEs for every policy, labelled first-quarter only. Multi-quarter value comes from simulate(). Stated plainly: targeting does not beat a uniform $5 offer |
| 13 | Base cut never evaluated on observed revenue / members | medium | accept | Added a descriptive treated-vs-Panem comparison (2019 vs 2018 spring-fall), labelled not causal |
| 14 | Elasticity at $15 includes Panem; retention at $15 never paid by treated members | medium | accept | Elasticities on treated cells only |
| 15 | Fit check is in-sample but described as validation | medium | accept | Renamed `fit_check_in_sample.*`, relative error added; out-of-sample backcast in Phase 3 |
| 16 | OPE SEs not in metrics.json; empty scenario units | low | accept | Added |
| 17 | Dead constant CALIBRATION_QUARTERS | low | accept | Removed |
| 18 | validate_policy checks order; bools accepted as ints | low | accept | Bool checks first; bools rejected for numeric and whole-number fields |
| 19 | simulate() branches untested | low | accept | Phase 3 tests |
| 20 | Eligibility-as-random (A2) only supported by observable balance | low | accept | Labelled as an assumption next to prospect-offer results (metrics notes; write-up) |

Net effect on conclusions:
- Prospects: a $5 offer to all new prospects is supported in the $12 era for every segment, including Cold.
- Members: neither "full price" nor "deep for everyone". Deeper discount at first and second renewal ($5 off),
  shallow for established members ($1 off), about 10-13% more LTV than the best single member discount across horizons and win-back settings.
- Base cut: direction only (sign-ups up in treated regions); no effect size is claimed.
