"""APPENDIX: the original model-based analysis, kept as a cross-check on the simple pipeline.

Not needed to produce or explain the results. It refits the same questions with regression models
(logit with region x quarter fixed effects and clustered errors, inverse-propensity weighting, a logit
difference-in-differences and event study, a fitted-curve simulator and a backtest), and writes
outputs/robustness/metrics.json. lorehaven.robustness.compare then sets its answers beside the simple ones.

Usage:  python -m lorehaven.robustness              (this, then the comparison)
Every reported number is written with a label: observed | estimate | assumption.

Analysis sample (one, documented): all regions and quarters 0-11 for the fixed-effect models
(Panem has no price variation and only pins its own fixed effects); treated regions in the $12 regime
(quarters 9-11) for the simulator and forward-looking segment results.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from lorehaven import data_prep
from lorehaven.robustness import backcast, models
from lorehaven.robustness.curve_simulator import SEGMENTS, PricingPolicy, load_model, logistic, member_value, simulate

RESULTS_DIR = data_prep.REPO_ROOT / "outputs" / "robustness"
# ASSUMPTION (recommendation): persistent arms of the rollout. Each prospect is assigned once and keeps the arm.
HOLDOUT_ARMS = {"5_off": 0.85, "list": 0.10, "3_off": 0.05}
SCENARIO_UNITS = {"ltv_per_1000_prospects": "$ per 1,000 prospects", "first_quarter_revenue_per_1000": "$ per 1,000 prospects",
                  "members_at_end_per_1000": "members per 1,000 prospects", "average_revenue_per_member_quarter": "$",
                  "average_quarterly_churn": "share per quarter", "discount_cost_per_1000": "$ per 1,000 prospects",
                  "share_of_member_quarters_discounted": "share"}


# Inputs:  raw CSVs via data_prep (full run), or the existing metrics.json (--derived-only)
# Outputs: outputs/results/metrics.json (single source of truth) and the CSV tables in outputs/results/


class MetricsRecorder:
    def __init__(self):
        """Start with an empty metrics dictionary."""
        self.metrics = {}

    def add(self, key, value, unit, label, source, note=""):
        """Record one metric with its unit, its label (observed, estimate or assumption), source and note."""
        if isinstance(value, (np.floating, np.integer, np.bool_)):
            value = value.item()
        if label not in ("observed", "estimate", "assumption"):
            raise ValueError(f"bad label {label}")
        self.metrics[key] = {"value": value, "unit": unit, "label": label, "source": source, "note": note}

    def save(self, path: Path):
        """Write all recorded metrics to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.metrics, indent=1, sort_keys=True))


def record_logit(rec, name, fit, source, note):
    """Record a fitted logit's coefficients, clustered standard errors and sample sizes."""
    for term in fit["coef"].index:
        rec.add(f"{name}.{term}.coef", fit["coef"][term], "log-odds per unit", "estimate", source, note)
        rec.add(f"{name}.{term}.se_clustered", fit["se_clustered"][term], "log-odds", "estimate", source)
    rec.add(f"{name}.n_rows", fit["n_rows"], "rows", "observed", source)
    rec.add(f"{name}.n_clusters", fit["n_clusters"], "clusters", "observed", source)


def record_price_rates(rec, table):
    """Observed sign-up / stay rates by price point and base-price era (treated regions, quarters >= 1)."""
    frames = []
    for outcome_name, rows, outcome in (("signup", models.prospects(table, True), "sign_up_flag"),
                                        ("retention", models.members(table, True), "stayed")):
        rows = rows[rows.quarter_index >= 1]
        rates = rows.groupby(["base_price", "membership_price"]).agg(n=(outcome, "size"), rate=(outcome, "mean")).reset_index()
        rates["outcome"] = outcome_name
        frames.append(rates)
        for r in rates.itertuples():
            rec.add(f"rates.{outcome_name}.base{r.base_price}.price{r.membership_price}", r.rate, "share", "observed",
                    "pipeline.record_price_rates", f"n={r.n}")
    pd.concat(frames).to_csv(RESULTS_DIR / "rates_by_price.csv", index=False)


def record_elasticities(rec, name, fit):
    """Point elasticity E = b * p * (1 - P), averaged over TREATED cells at each price (Panem excluded)."""
    cells = fit["cells"]
    cells = cells[~cells.region_quarter.str.startswith(data_prep.CONTROL_REGION)]
    for price, group in cells.groupby("price"):
        elasticity = np.average(fit["coef"]["price"] * price * (1 - group.predicted), weights=group.trials)
        rec.add(f"elasticity.{name}.price{int(price)}", elasticity, "% change per 1% price", "estimate", "lorehaven.models",
                "Treated regions only; E = beta * p * (1 - P)")


def record_base_cut(rec, table):
    """Record the difference-in-differences, pre-trend test and event study for the 2019 base cut."""
    src = "lorehaven.models.base_cut_did"
    did = models.base_cut_did(table)
    d = did["did"]
    note = ("DIRECTION CHECK ONLY: prospects at list price, region + quarter FE, SE clustered by sub-region (20 clusters, "
            "6 in Panem); pre-trend test fails, so no effect size is claimed")
    rec.add("did.delta", d["coef"]["treated_x_post"], "log-odds", "estimate", src, note)
    rec.add("did.delta_se_subregion_clustered", d["se_clustered"]["treated_x_post"], "log-odds", "estimate", src, note)
    rec.add("did.pretrend_p_value", did["pretrend_test"]["p_value"], "p", "estimate", src,
            "Joint test that pre-cut treated x quarter terms are zero (sub-region clustered)")
    event = did["event"]
    pd.DataFrame({"coef": event["coef"], "se_subregion_clustered": event["se_clustered"]}).to_csv(RESULTS_DIR / "event_study.csv")
    for term in event["coef"].index:
        rec.add(f"event_study.{term}", event["coef"][term], "log-odds vs q8", "estimate", src, note)
        rec.add(f"event_study.{term}.se", event["se_clustered"][term], "log-odds", "estimate", src)
    observed = models.base_cut_observed_comparison(table)
    observed.to_csv(RESULTS_DIR / "base_cut_observed.csv", index=False)
    for r in observed.itertuples():
        for col in ("members_per_customer_quarter", "revenue_per_customer_quarter", "revenue_per_member_quarter"):
            rec.add(f"base_cut_observed.{r.group}.{r.period}.{col}", getattr(r, col), "$ or share", "observed",
                    "lorehaven.models.base_cut_observed_comparison",
                    "DESCRIPTIVE ONLY: 2019 spring-fall vs 2018 spring-fall; not causal")


def record_segments(rec, table):
    """Record the would-join-anyway vs persuadable split, offer efficiency and off-policy results by segment."""
    src = "lorehaven.models"
    for era_name, base in (("all_eras", None), ("base12", 12)):
        uplift = models.uplift_by_segment(table, base_price=base)
        uplift.to_csv(RESULTS_DIR / f"uplift_by_segment_{era_name}.csv", index=False)
        for row in uplift.itertuples():
            for col in ("share_of_prospects", "p0_list", "uplift_1", "uplift_3", "uplift_5", "already_sold",
                        "persuadable_at_5", "out_of_reach_at_5", "incremental_share_at_5"):
                label = "observed" if col in ("share_of_prospects", "p0_list", "already_sold") else "estimate"
                rec.add(f"uplift.{era_name}.{row.segment}.{col}", getattr(row, col), "share", label, src,
                        "Treated prospects; LPM with region x quarter FE; decomposition ASSUMES no one is deterred by a "
                        "discount and (A2) offer eligibility as good as random")
    prospect = models.prospect_discount_efficiency(table)
    prospect.to_csv(RESULTS_DIR / "prospect_discount_efficiency.csv", index=False)
    for r in prospect.itertuples():
        key = f"efficiency.prospect.{r.segment}.base{r.base_price}.depth{r.discount_depth}"
        rec.add(key + ".signup_rate", r.signup_rate, "share", "observed", src, f"n={r.n}; depth randomized within era")
        rec.add(key + ".revenue_per_prospect", r.revenue_per_prospect, "$ per prospect-quarter", "observed", src)
        if r.discount_depth > 0:
            rec.add(key + ".already_sold_share", r.already_sold_share, "share of joiners", "estimate", src,
                    "list-price rate / offered rate; ASSUMES no one is deterred by a discount")
            rec.add(key + ".discount_to_already_sold_per_1000", r.discount_to_already_sold_per_1000, "$ per 1,000 offered", "estimate", src)
            rec.add(key + ".discount_per_incremental_joiner", r.discount_per_incremental_joiner, "$", "estimate", src)
        if r.is_revenue_best_depth:
            rec.add(f"efficiency.prospect.{r.segment}.base{r.base_price}.revenue_best_depth", int(r.discount_depth), "$ off",
                    "estimate", src, "Depth with highest first-quarter revenue per prospect among $0-$5")
    member = models.member_discount_efficiency(table)
    member.to_csv(RESULTS_DIR / "member_discount_efficiency.csv", index=False)
    for r in member.itertuples():
        key = f"efficiency.member.{r.segment}.base{r.base_price}.price{r.membership_price}"
        rec.add(key + ".stay_rate", r.stay_rate, "share", "observed", src, f"n={r.n}")
        rec.add(key + ".extra_stayers_vs_shallowest", r.extra_stayers_vs_shallowest, "share", "observed", src)

    ope, propensities = models.off_policy_evaluation(table)
    ope.to_csv(RESULTS_DIR / "off_policy_evaluation.csv", index=False)
    for action, p in propensities.items():
        rec.add(f"ope.logging_propensity.depth{action}", p, "share", "observed", src, "$12 regime, q9-q11")
    for row in ope.itertuples():
        for col in ("signup_rate", "first_quarter_revenue"):
            note = "Inverse-propensity estimate, treated prospects, $12 regime (q9-q11), FIRST QUARTER ONLY (not LTV)"
            rec.add(f"ope.{row.policy}.{col}", getattr(row, col), "per prospect-quarter", "estimate", src, note)
            rec.add(f"ope.{row.policy}.{col}_se", getattr(row, col + "_se"), "per prospect-quarter", "estimate", src)

    pull = models.pull_forward_check(table)
    for segment, values in pull.items():
        for name, value in values.items():
            rec.add(f"pull_forward.{segment}.{name}", value, "share per $", "estimate", "lorehaven.models.pull_forward_check",
                    "Prospects who did not join: effect of this quarter's depth on next quarter's sign-up")


def record_simulator_parameters(rec, table):
    """Record the simulator's response curves, segment shares and tested price ranges."""
    src = "lorehaven.models.simulator_fits"
    fits = models.simulator_fits(table)
    note = ("Average-quarter logit, treated regions in the $12 regime (q9-q11), no quarter FE (price randomized "
            "independently of quarter). ASSUMPTION: 2019 conditions persist; no seasonality.")
    high_share = fits["share_high_podcast_among_never_prospects"]
    rec.add("simulator.calibrated_base_price", 12, "$", "observed", src)
    rec.add("simulator.tested_prospect_price_min", fits["tested_prospect_price_range"][0], "$", "observed", src)
    rec.add("simulator.tested_prospect_price_max", fits["tested_prospect_price_range"][1], "$", "observed", src)
    rec.add("simulator.tested_member_price_min", fits["tested_member_price_range"][0], "$", "observed", src)
    rec.add("simulator.tested_member_price_max", fits["tested_member_price_range"][1], "$", "observed", src)
    prospects_now = models.prospects(models.current_regime_rows(table))
    rec.add("simulator.tested_offer_share", float(prospects_now.discount_flag.mean()), "share", "observed", src,
            "Share of treated prospects offered a discount, q9-q11")
    for segment, share in (("high_podcast", high_share), ("low_podcast", 1 - high_share)):
        rec.add(f"simulator.{segment}.share_of_prospects", share, "share", "observed", src,
                "Share among never-member prospects, treated regions, q9-q11")
        for part, fit in fits[segment].items():
            rec.add(f"simulator.{segment}.{part}_intercept", float(fit["fixed_effects"].iloc[0]), "log-odds", "estimate", src, note)
            rec.add(f"simulator.{segment}.{part}_price_slope", fit["coef"]["price"], "log-odds per $", "estimate", src, note)
            rec.add(f"simulator.{segment}.{part}_price_se_clustered", fit["se_clustered"]["price"], "log-odds per $", "estimate", src)
            rec.add(f"simulator.{segment}.{part}_n_rows", fit["n_rows"], "rows", "observed", src)


def record_model_fit_check(rec, table, model):
    """IN-SAMPLE fit check: predicted vs observed rates on the same q9-q11 data the simulator was fit on.
    Out-of-sample accuracy is measured by the backcast (lorehaven.backcast)."""
    rows = models.current_regime_rows(table)
    checks = []
    for segment, flag in (("high_podcast", 1), ("low_podcast", 0)):
        m = model.segments[segment]
        seg = rows[rows.is_high_podcast == flag]
        groups = [("never", seg[(seg.is_prospect == 1) & (seg.is_lapsed == 0)], "sign_up_flag",
                   lambda p, m=m: logistic(m.join_never_intercept + m.join_never_price_slope * p)),
                  ("lapsed", seg[seg.is_lapsed == 1], "sign_up_flag",
                   lambda p, m=m: logistic(m.join_lapsed_intercept + m.join_lapsed_price_slope * p))]
        for group, (low, high) in models.TENURE_GROUPS.items():
            groups.append((f"member_{group}", seg[(seg.status == "member") & seg.member_tenure.between(low, high)], "stayed",
                           lambda p, m=m, g=group: m.stay_probability(g, p)))
        for status, group_rows, outcome, predict in groups:
            for price, cell in group_rows.groupby("membership_price"):
                checks.append(dict(segment=segment, status=status, price=int(price), n=len(cell),
                                   observed=cell[outcome].mean(), predicted=predict(price)))
    checks = pd.DataFrame(checks)
    checks["abs_error"] = (checks.predicted - checks.observed).abs()
    checks["relative_error"] = checks.abs_error / checks.observed
    checks.to_csv(RESULTS_DIR / "model_fit_check_in_sample.csv", index=False)
    src = "pipeline.record_model_fit_check"
    for r in checks.itertuples():
        key = f"fit_check_in_sample.{r.segment}.{r.status}.price{r.price}"
        rec.add(key + ".observed", r.observed, "share", "observed", src, f"q9-q11, treated, n={r.n}")
        rec.add(key + ".predicted", r.predicted, "share", "estimate", src)
    note = "IN-SAMPLE (same q9-q11 data used to fit); by segment, status/tenure, price"
    rec.add("fit_check_in_sample.mean_abs_error", np.average(checks.abs_error, weights=checks.n), "rate points", "estimate", src, note)
    rec.add("fit_check_in_sample.max_abs_error", checks.abs_error.max(), "rate points", "estimate", src, note)
    rec.add("fit_check_in_sample.max_relative_error", checks.relative_error.max(), "share of observed", "estimate", src, note)


def record_backcast(rec, table):
    """Run the backcasts, save backcast.csv and record their error figures."""
    results = backcast.run_backcast(table)
    pd.concat([frame.assign(run=name) for name, frame in results.items()]).to_csv(RESULTS_DIR / "backcast.csv", index=False)
    notes = {"in_sample": "Fit on 2017-2019, replayed from launch (accounting / fit check, not validation)",
             "out_of_sample_same_season": "Fit on 2017-2018, forecast 2019 from actual end-2018 state; baseline = same season 2018",
             "out_of_sample_avg_2018": ("Fit on 2017-2018, forecast 2019 from actual end-2018 state; baseline = average 2018 "
                                        "quarter. Chosen AFTER the same-season rule failed; both reported")}
    for key, value in backcast.summarize(results).items():
        run = key.split(".")[0]
        unit = "members" if "total_members" in key else "share"
        rec.add(f"backcast.{key}", value, unit, "estimate", "lorehaven.backcast", notes[run])


def record_headlines(rec):
    """Derived numbers quoted in the write-up, computed here so every quoted number is a metrics.json key."""
    m = rec.metrics
    value = lambda key: m[key]["value"]
    src = "pipeline.record_headlines"
    ltv = lambda name: value(f"scenario.{name}.ltv_per_1000_prospects")
    recommended, today = "prospects_5_off_no_winback_new_5_off_established_1_off", "status_quo_2019"
    uniform_best = max((f"prospects_5_off_no_winback_members_{k}_off" for k in range(1, 6)), key=ltv)
    rows = {
        "ltv_recommended_vs_today_pct": (ltv(recommended) / ltv(today) - 1, "Recommended vs today's policy, 12 quarters"),
        "ltv_recommended_vs_best_uniform_pct": (ltv(recommended) / ltv(uniform_best) - 1,
                                                f"Recommended vs best single member discount ({uniform_best}), 12 quarters"),
        "ltv_recommended_vs_today_pct_h40": (value(f"scenario.{recommended}.h40.ltv_per_1000_prospects")
                                             / value(f"scenario.{today}.h40.ltv_per_1000_prospects") - 1, "40 quarters"),
        "ltv_recommended_with_winback_vs_today_pct": (ltv("prospects_5_off_winback_new_5_off_established_1_off") / ltv(today) - 1,
                                                      "Same as recommended but former members also get the offer"),
        "signup_odds_change_per_dollar_off": (np.exp(-value("acquisition.price.coef")) - 1, "exp(-beta) - 1, FE logit"),
        "retention_odds_change_per_dollar_off": (np.exp(-value("retention.price.coef")) - 1, "exp(-beta) - 1, FE logit"),
    }
    for group in ("treated", "panem"):
        for measure in ("revenue_per_customer_quarter", "members_per_customer_quarter", "revenue_per_member_quarter"):
            before = value(f"base_cut_observed.{group}.2018_spring_fall.{measure}")
            after = value(f"base_cut_observed.{group}.2019_spring_fall.{measure}")
            rows[f"base_cut_{group}_{measure}_change_pct"] = (after / before - 1, "DESCRIPTIVE: 2019 vs 2018 spring-fall")
    for segment in ("high_podcast", "low_podcast"):
        pf = lambda name: value(f"pull_forward.{segment}.{name}")
        rows[f"pull_forward_offset_share_{segment}"] = (abs(pf("next_quarter_effect_per_dollar_now") / pf("same_quarter_effect_per_dollar")),
                                                        "Next-quarter loss as a share of the same-quarter gain per $ of depth")
    # Holdout design (recommendation): $5 offer default with a persistent randomized holdout.
    # Precision of the $5-vs-list sign-up comparison at the same prospect traffic, today's logged shares vs the design.
    #   SE  proportional to  sqrt( v_5 / s_5 + v_0 / s_0 )
    #   s_5, s_0 = share of prospects at $5 off and at list price;  v = outcome variance in each arm.
    # Equal-variance version: v_5 = v_0.  Bernoulli version: v = p (1 - p), p = observed sign-up rate at $7 and $12 ($12 era).
    today_shares = (value("ope.logging_propensity.depth5"), value("ope.logging_propensity.depth0"))
    proposed_shares = (HOLDOUT_ARMS["5_off"], HOLDOUT_ARMS["list"])
    p_offer, p_list = value("rates.signup.base12.price7"), value("rates.signup.base12.price12")
    se_equal = lambda shares: np.sqrt(1 / shares[0] + 1 / shares[1])
    se_bernoulli = lambda shares: np.sqrt(p_offer * (1 - p_offer) / shares[0] + p_list * (1 - p_list) / shares[1])
    rows["holdout_design_se_ratio_vs_today"] = (se_equal(proposed_shares) / se_equal(today_shares),
                                                "SE of $5-vs-list uplift, design vs today's logged shares; APPROXIMATION: equal outcome variance")
    rows["holdout_design_se_ratio_vs_today_bernoulli"] = (se_bernoulli(proposed_shares) / se_bernoulli(today_shares),
                                                          "Same ratio with Bernoulli variance p(1-p) at observed $12-era sign-up rates")
    # Value of the rollout itself: arms are persistent, so under the simulator its LTV is the share-weighted LTV of each arm.
    arm_scenario = lambda arm: f"prospects_{arm}_no_winback_new_5_off_established_1_off"
    for suffix, label in (("", "12 quarters"), (".h40", "40 quarters")):
        design = sum(share * value(f"scenario.{arm_scenario(arm)}{suffix}.ltv_per_1000_prospects") for arm, share in HOLDOUT_ARMS.items())
        today_ltv = value(f"scenario.{today}{suffix}.ltv_per_1000_prospects")
        tag = suffix.replace(".", "_")
        rows[f"holdout_design_ltv_per_1000{tag}"] = (design, f"$: 85% $5 / 10% list / 5% $3 off, persistent arms, {label}, under the simulator")
        rows[f"holdout_design_ltv_vs_today_pct{tag}"] = (design / today_ltv - 1, f"85/10/5 rollout vs today's policy, {label}")
    gain = value("ope.offer_all_5_off.first_quarter_revenue") - value("ope.no_offers.first_quarter_revenue")
    rows["holdout_cost_per_prospect_quarter_at_10pct"] = (0.10 * gain, "$: 10% of prospects at list forgo the $5-offer gain (OPE, first quarter)")
    for key, (number, note) in rows.items():
        unit = "$" if key.startswith(("holdout_cost", "holdout_design_ltv_per")) else "share"
        rec.add(f"headline.{key}", float(number), unit, "estimate", src, note)
    for arm, share in HOLDOUT_ARMS.items():
        rec.add(f"assumption.holdout_arm_share.{arm}", share, "share of new prospects", "assumption", src,
                "Recommended rollout: persistent arms, each prospect assigned once")


def record_member_value(rec, model):
    """Value of one established member by price and horizon (steady state ignores re-joining)."""
    for segment, segment_model in model.segments.items():
        for price in range(7, 13):
            for horizon in (4, 12, 40, None):
                name = "steady_state" if horizon is None else f"h{horizon}"
                rec.add(f"member_value.{segment}.price{price}.{name}", member_value(segment_model, price, horizon),
                        "$ per established member", "estimate", "lorehaven.simulate.member_value",
                        "Established member charged this price every quarter; ignores churn-and-rejoin")


def scenario_policies() -> dict:
    """Return the named pricing policies compared in the write-up and figures."""
    everyone = lambda value: {s: value for s in SEGMENTS}
    scenarios = {"status_quo_2019": PricingPolicy(base_price=12, random_depths=True),
                 "no_discounts_base12": PricingPolicy(base_price=12, offer_share=everyone(0.0), prospect_discount=everyone(0.0),
                                                      new_member_discount=0.0, established_member_discount=0.0)}
    for winback, label in ((True, "winback"), (False, "no_winback")):
        for member_off in range(0, 6):     # same discount for every member
            scenarios[f"prospects_5_off_{label}_members_{member_off}_off"] = PricingPolicy(
                base_price=12, offer_share=everyone(1.0), prospect_discount=everyone(5.0), new_member_discount=float(member_off),
                established_member_discount=float(member_off), lapsed_get_offers=winback)
        for new_off in (3, 4, 5):          # tenure-based: deeper for first two renewals, shallow afterwards
            for established_off in (1, 2):
                scenarios[f"prospects_5_off_{label}_new_{new_off}_off_established_{established_off}_off"] = PricingPolicy(
                    base_price=12, offer_share=everyone(1.0), prospect_discount=everyone(5.0), new_member_discount=float(new_off),
                    established_member_discount=float(established_off), lapsed_get_offers=winback)
    # Holdout arms of the recommended rollout: same member pricing, different introductory offer.
    for arm, (share, depth) in {"list": (0.0, 0.0), "3_off": (1.0, 3.0)}.items():
        scenarios[f"prospects_{arm}_no_winback_new_5_off_established_1_off"] = PricingPolicy(
            base_price=12, offer_share=everyone(share), prospect_discount=everyone(depth),
            new_member_discount=5.0, established_member_discount=1.0, lapsed_get_offers=False)
    scenarios["high_podcast_only_5_off_no_winback_new_5_off_established_1_off"] = PricingPolicy(
        base_price=12, offer_share={"high_podcast": 1.0, "low_podcast": 0.0}, prospect_discount=everyone(5.0),
        new_member_discount=5.0, established_member_discount=1.0, lapsed_get_offers=False)
    return scenarios


def record_scenarios(rec, model):
    """Simulate every named policy at 12, 20 and 40 quarters and record the results."""
    for name, policy in scenario_policies().items():
        for horizon in (12, 20, 40):
            policy.horizon_quarters = horizon
            result = simulate(policy, model)
            suffix = "" if horizon == 12 else f".h{horizon}"
            for kpi, value in result["kpis"].items():
                if horizon != 12 and kpi != "ltv_per_1000_prospects":
                    continue
                note = f"{horizon} quarters, $12-regime calibration, d=0"
                if result["warnings"]:
                    note += "; WARNINGS: " + " | ".join(result["warnings"])
                rec.add(f"scenario.{name}{suffix}.{kpi}", value, SCENARIO_UNITS[kpi], "estimate", "lorehaven.simulate", note)


def main():
    """Run the full analysis from the raw data and write metrics.json, then re-verify the earlier findings."""
    rec = MetricsRecorder()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # 1. Load and clean the raw data into one customer x quarter table (status, prices, known data gaps set to missing)
    table = data_prep.build_analysis_table()
    src = "lorehaven.models"
    # 2. Record the stated assumptions and the data size, so every later number can be traced back
    rec.add("assumption.season_order", "winter->spring->summer->fall", "", "assumption", "data_prep")
    rec.add("assumption.launch_quarter", "2017 winter; no members before", "", "assumption", "data_prep")
    rec.add("assumption.podcast_cutoff", data_prep.PODCAST_SEGMENT_CUTOFF, "score", "assumption", "data_prep")
    rec.add("data.customers", table.customer_id.nunique(), "customers", "observed", "data_prep")
    rec.add("data.panel_rows", len(table), "rows", "observed", "data_prep")

    # 3. Observed sign-up and stay rates at each price (the raw evidence before any model)
    record_price_rates(rec, table)
    # 4. MAIN RESULT: price response from the randomized discounts (logit, region x quarter FE, clustered SE)
    note = "Region x quarter FE, customer-clustered SE; identification: randomized offer/depth within region x quarter"
    acquisition = models.acquisition_model(table)
    retention = models.retention_model(table)
    record_logit(rec, "acquisition", acquisition, src, note)
    record_logit(rec, "retention", retention, src, note)
    record_elasticities(rec, "acquisition", acquisition)
    record_elasticities(rec, "retention", retention)
    # 5. What the randomized curve predicts for the $3 base cut (the benchmark the DiD is compared against)
    rec.add("did.randomized_prediction_delta", float(-3 * acquisition["coef"]["price"]), "log-odds", "estimate", src,
            "-3 x acquisition price coefficient: what the randomized curve implies for a $3 cut")
    # 6. Separate price-response models per podcast segment: sign-up (never and former members) and retention
    for segment, fits in models.segment_models(table).items():
        for part, fit in fits.items():
            record_logit(rec, f"segment.{segment}.{part}", fit, src, note + "; own FE per segment and status")
    # 7. Robustness: same models with quarter-only fixed effects, discounting regions only
    record_logit(rec, "robustness.acquisition_quarter_fe",
                 models.acquisition_model(table, fixed_effects=("quarter_index",), treated_only=True), src, "Quarter FE only, treated")
    record_logit(rec, "robustness.retention_quarter_fe",
                 models.retention_model(table, fixed_effects=("quarter_index",), treated_only=True), src, "Quarter FE only, treated")

    # 8. Supporting evidence on the 2019 $15 -> $12 cut: DiD vs Panem, pre-trend test, event study (direction only)
    record_base_cut(rec, table)
    # 9. Who the offer actually wins: would-join-anyway vs persuadable by segment, offer efficiency, off-policy values
    record_segments(rec, table)
    # 10. Calibrate the simulator on the $12 era (q9-q11) and save, because the simulator reads its parameters from metrics.json
    record_simulator_parameters(rec, table)
    rec.save(RESULTS_DIR / "metrics.json")
    model = load_model(RESULTS_DIR / "metrics.json")
    # 11. Revenue from one established member at each price and horizon (simple steady-state view)
    record_member_value(rec, model)
    # 12. In-sample check: do the simulator's curves reproduce the 2019 ($12 era) rates they were fit on?
    record_model_fit_check(rec, table, model)
    # 13. Simulate every named policy (today, recommended, alternatives, holdout arms) at 12, 20 and 40 quarters
    record_scenarios(rec, model)
    # 14. Validation: replay history with the simulator (fit on 2017-18, predict 2019) and record the errors
    record_backcast(rec, table)
    # 15. Derived numbers quoted in the write-up (headline gains, holdout value and precision, pull-forward shares)
    record_headlines(rec)
    # 16. Write the single source of truth that the write-up, tool and notebook all read
    rec.save(RESULTS_DIR / "metrics.json")
    print(f"wrote {len(rec.metrics)} metrics to {RESULTS_DIR / 'metrics.json'}")
    # 17. Independently re-derive the early exploration's claims and add the match counts to metrics.json
    from lorehaven.robustness import verify_findings   # local import: verify_findings imports this module
    verify_findings.main()


def refresh_derived():
    """Re-run only the steps that need metrics.json, not the raw data: simulator scenarios and headline numbers.
    Usage:  python -m lorehaven.pipeline --derived-only"""
    rec = MetricsRecorder()
    rec.metrics = json.loads((RESULTS_DIR / "metrics.json").read_text())
    record_scenarios(rec, load_model(RESULTS_DIR / "metrics.json"))
    record_headlines(rec)
    rec.save(RESULTS_DIR / "metrics.json")
    print(f"refreshed scenarios and headlines; {len(rec.metrics)} metrics in {RESULTS_DIR / 'metrics.json'}")


if __name__ == "__main__":
    import sys
    refresh_derived() if "--derived-only" in sys.argv else main()
