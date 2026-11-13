"""Run the full analysis and write outputs/results/metrics.json (single source of truth).

Usage:  python -m lorehaven.pipeline      (also re-runs the FINDINGS.md verification at the end)
Every reported number is written with a label: observed | estimate | assumption.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from lorehaven import data_prep, models
from lorehaven.simulate import PricingPolicy, SEGMENTS, load_model, logistic, member_value, simulate

RESULTS_DIR = data_prep.REPO_ROOT / "outputs" / "results"
CALIBRATION_QUARTERS = range(8, 12)   # 2019: the current $12 regime (q8 is still $15; FE are price-free baselines)


class MetricsRecorder:
    def __init__(self):
        self.metrics = {}

    def add(self, key, value, unit, label, source, note=""):
        if isinstance(value, (np.floating, np.integer)):
            value = value.item()
        if label not in ("observed", "estimate", "assumption"):
            raise ValueError(f"bad label {label}")
        self.metrics[key] = {"value": value, "unit": unit, "label": label, "source": source, "note": note}

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.metrics, indent=1, sort_keys=True))


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


def record_logit(rec, name, fit, source, note):
    for term in fit["coef"].index:
        rec.add(f"{name}.{term}.coef", fit["coef"][term], "log-odds per unit", "estimate", source, note)
        rec.add(f"{name}.{term}.se_clustered", fit["se_clustered"][term], "log-odds", "estimate", source)
    rec.add(f"{name}.n_rows", fit["n_rows"], "rows", "observed", source)
    rec.add(f"{name}.n_customers", fit["n_clusters"], "customers", "observed", source)


def record_simulator_parameters(rec, table, simulator_fits):
    src = "pipeline.record_simulator_parameters"
    customers_2019 = table[(table.year == 2019) & (table.is_treated_region == 1)].drop_duplicates("customer_id")
    high_share = customers_2019.is_high_podcast.mean()
    note = ("Average-quarter logit per segment and status, fit on treated regions in the $12 regime (q9-q11), "
            "no quarter FE (price randomized independently of quarter). ASSUMPTION: 2019 conditions persist.")
    for segment, share in (("high_podcast", high_share), ("low_podcast", 1 - high_share)):
        fits = simulator_fits[segment]
        intercept = lambda fit: float(fit["fixed_effects"].iloc[0])
        values = dict(share_of_prospects=share,
                      join_never_intercept=intercept(fits["join_never"]), join_never_price_slope=fits["join_never"]["coef"]["price"],
                      join_lapsed_intercept=intercept(fits["join_lapsed"]), join_lapsed_price_slope=fits["join_lapsed"]["coef"]["price"],
                      stay_intercept=intercept(fits["retention"]), stay_price_slope=fits["retention"]["coef"]["price"])
        for name, value in values.items():
            label = "observed" if name == "share_of_prospects" else "estimate"
            rec.add(f"simulator.{segment}.{name}", value, "share" if "share" in name else "log-odds", label, src, note)
        for part, fit in fits.items():
            rec.add(f"simulator.{segment}.{part}.price_se_clustered", fit["se_clustered"]["price"], "log-odds", "estimate", src)


def record_model_fit_check(rec, table, model):
    """Model-predicted vs observed 2019 rates by segment, status and price (treated regions, quarters 9-11, $12 base)."""
    rows = table[(table.is_treated_region == 1) & table.quarter_index.isin([9, 10, 11])]
    checks = []
    for segment, flag in (("high_podcast", 1), ("low_podcast", 0)):
        m = model[segment]
        groups = (("never", models.prospects(rows[rows.is_high_podcast == flag]).query("is_lapsed == 0"), "sign_up_flag",
                   m.join_never_intercept, m.join_never_price_slope),
                  ("lapsed", models.prospects(rows[rows.is_high_podcast == flag]).query("is_lapsed == 1"), "sign_up_flag",
                   m.join_lapsed_intercept, m.join_lapsed_price_slope),
                  ("member", models.members(rows[rows.is_high_podcast == flag]), "stayed", m.stay_intercept, m.stay_price_slope))
        for status, group, outcome, intercept, slope in groups:
            for price, cell in group.groupby("membership_price"):
                predicted = logistic(intercept + slope * price)
                checks.append(dict(segment=segment, status=status, price=int(price), n=len(cell),
                                   observed=cell[outcome].mean(), predicted=predicted))
    checks = pd.DataFrame(checks)
    checks["abs_error"] = (checks.predicted - checks.observed).abs()
    checks.to_csv(RESULTS_DIR / "model_fit_check_2019.csv", index=False)
    weighted = np.average(checks.abs_error, weights=checks.n)
    rec.add("fit_check.mean_abs_error_2019", weighted, "share (rate points)", "estimate", "pipeline.record_model_fit_check",
            "Row-weighted mean |predicted - observed| over 2019 $12-era cells (q9-11) by segment, status, price")
    rec.add("fit_check.max_abs_error_2019", checks.abs_error.max(), "share (rate points)", "estimate", "pipeline.record_model_fit_check")


def record_discount_efficiency(rec, table):
    src = "lorehaven.models"
    prospect = models.prospect_discount_efficiency(table)
    prospect.to_csv(RESULTS_DIR / "prospect_discount_efficiency.csv", index=False)
    for r in prospect.itertuples():
        key = f"efficiency.prospect.{r.segment}.base{r.base_price}.depth{r.discount_depth}"
        rec.add(key + ".signup_rate", r.signup_rate, "share", "observed", src, f"n={r.n}; randomized within era")
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


def record_member_value(rec, model):
    """Value of one current member by price and horizon (shows why steady-state and 12-quarter answers differ)."""
    for segment, segment_model in model.items():
        for price in range(7, 13):
            for horizon in (4, 12, 40, None):
                name = "steady_state" if horizon is None else f"h{horizon}"
                rec.add(f"member_value.{segment}.price{price}.{name}", member_value(segment_model, price, horizon),
                        "$ per current member", "estimate", "lorehaven.simulate.member_value",
                        "Member charged this price every quarter; steady state assumes members never age out")


SCENARIOS = {
    "status_quo_2019": PricingPolicy(base_price=12, random_depths=True),
    "status_quo_base15": PricingPolicy(base_price=15, random_depths=True),
    "high_podcast_only_5_off_members_5_off": PricingPolicy(base_price=12, offer_share={"high_podcast": 1.0, "low_podcast": 0.0},
                                                           prospect_discount={s: 5.0 for s in SEGMENTS}, member_discount=5.0),
    **{f"prospects_5_off_members_{k}_off": PricingPolicy(base_price=12, offer_share={s: 1.0 for s in SEGMENTS},
                                                         prospect_discount={s: 5.0 for s in SEGMENTS}, member_discount=float(k))
       for k in range(0, 6)},
    **{f"prospects_5_off_no_winback_members_{k}_off": PricingPolicy(
        base_price=12, offer_share={s: 1.0 for s in SEGMENTS}, prospect_discount={s: 5.0 for s in SEGMENTS},
        member_discount=float(k), lapsed_get_offers=False) for k in range(0, 6)},
    "no_discounts_base12": PricingPolicy(base_price=12, offer_share={s: 0.0 for s in SEGMENTS},
                                         prospect_discount={s: 0.0 for s in SEGMENTS}, member_discount=0.0),
}


def main():
    rec = MetricsRecorder()
    table = data_prep.build_analysis_table()
    src = "lorehaven.models"
    rec.add("assumption.season_order", "winter->spring->summer->fall", "", "assumption", "data_prep")
    rec.add("assumption.launch_quarter", "2017 winter; no members before", "", "assumption", "data_prep")
    rec.add("assumption.podcast_cutoff", data_prep.PODCAST_SEGMENT_CUTOFF, "score", "assumption", "data_prep")
    rec.add("data.customers", table.customer_id.nunique(), "customers", "observed", "data_prep")
    rec.add("data.panel_rows", len(table), "rows", "observed", "data_prep")

    record_price_rates(rec, table)
    note = "Region x quarter FE; identification: randomized offer/depth within region x quarter"
    acq = models.acquisition_model(table); record_logit(rec, "acquisition", acq, src, note)
    ret = models.retention_model(table); record_logit(rec, "retention", ret, src, note)
    segment_fits = models.segment_models(table)
    for segment, fits in segment_fits.items():
        for part, fit in fits.items():
            record_logit(rec, f"segment.{segment}.{part}", fit, src, note + "; own FE per segment and status")
    acq_qfe = models.acquisition_model(table, fixed_effects=("quarter_index",), treated_only=True)
    record_logit(rec, "robustness.acquisition_quarter_fe", acq_qfe, src, "Quarter FE only, treated regions")
    ret_qfe = models.retention_model(table, fixed_effects=("quarter_index",), treated_only=True)
    record_logit(rec, "robustness.retention_quarter_fe", ret_qfe, src, "Quarter FE only, treated regions")

    for name, fit in (("acquisition", acq), ("retention", ret)):  # point elasticity E = b * p * (1 - P) at observed cells
        cells = fit["cells"]
        cells = cells[cells.price.between(7, 15)]
        for price, group in cells.groupby("price"):
            elasticity = np.average(fit["coef"]["price"] * price * (1 - group.predicted), weights=group.trials)
            rec.add(f"elasticity.{name}.price{int(price)}", elasticity, "% change per 1% price", "estimate", src,
                    "E = beta * p * (1 - P), averaged over cells at that price")

    did = models.base_cut_did(table)
    d = did["did"]
    rec.add("did.delta", d["coef"]["treated_x_post"], "log-odds", "estimate", src,
            "Prospects at list price; region + quarter FE; ASSUMPTION parallel trends with Panem as the only control")
    rec.add("did.delta_se_clustered", d["se_clustered"]["treated_x_post"], "log-odds", "estimate", src)
    rec.add("did.odds_ratio", float(np.exp(d["coef"]["treated_x_post"])), "ratio", "estimate", src)
    rec.add("did.randomized_prediction_delta", float(-3 * acq["coef"]["price"]), "log-odds", "estimate", src,
            "-3 x acquisition price coefficient: what the randomized curve implies for a $3 cut")
    rec.add("did.randomized_prediction_odds_ratio", float(np.exp(-3 * acq["coef"]["price"])), "ratio", "estimate", src)
    rec.add("did.pretrend_chi2", did["pretrend_test"]["chi2"], "chi2", "estimate", src)
    rec.add("did.pretrend_p_value", did["pretrend_test"]["p_value"], "p", "estimate", src,
            "Joint test that pre-cut treated x quarter terms are zero (customer-clustered)")
    event = did["event"]
    pd.DataFrame({"coef": event["coef"], "se_clustered": event["se_clustered"]}).to_csv(RESULTS_DIR / "event_study.csv")
    for term in event["coef"].index:
        rec.add(f"event_study.{term}", event["coef"][term], "log-odds vs q8", "estimate", src)

    uplift = models.uplift_by_segment(table)
    uplift.to_csv(RESULTS_DIR / "uplift_by_segment.csv", index=False)
    for row in uplift.itertuples():
        for col in ("share_of_prospects", "p0_list", "uplift_1", "uplift_3", "uplift_5", "already_sold",
                    "persuadable_at_5", "out_of_reach_at_5", "incremental_share_at_5"):
            label = "observed" if col in ("share_of_prospects", "p0_list", "already_sold") else "estimate"
            rec.add(f"uplift.{row.segment}.{col}", getattr(row, col), "share", label, src,
                    "Treated prospects, LPM with region x quarter FE; decomposition ASSUMES no one is deterred by a discount")
        rec.add(f"uplift.{row.segment}.all_uplifts_non_negative", bool(row.all_uplifts_non_negative), "bool", "estimate", src)

    ope, propensities = models.off_policy_evaluation(table)
    ope.to_csv(RESULTS_DIR / "off_policy_evaluation.csv", index=False)
    for action, p in propensities.items():
        rec.add(f"ope.logging_propensity.depth{action}", p, "share", "observed", src)
    for row in ope.itertuples():
        for col in ("signup_rate", "first_quarter_revenue"):
            rec.add(f"ope.{row.policy}.{col}", getattr(row, col), "per prospect-quarter", "estimate", src,
                    "Inverse-propensity estimate, treated prospects, first quarter only (not LTV)")

    record_discount_efficiency(rec, table)
    record_simulator_parameters(rec, table, models.simulator_fits(table))
    rec.save(RESULTS_DIR / "metrics.json")            # simulator reads its parameters from here
    model = load_model(RESULTS_DIR / "metrics.json")
    record_member_value(rec, model)
    record_model_fit_check(rec, table, model)
    for name, policy in SCENARIOS.items():
        result = simulate(policy, model)
        for kpi, value in result["kpis"].items():
            rec.add(f"scenario.{name}.{kpi}", value, "", "estimate", "lorehaven.simulate",
                    "12 quarters, 2019-calibrated, d=0" + ("; WARNINGS: " + " | ".join(result["warnings"]) if result["warnings"] else ""))
    rec.save(RESULTS_DIR / "metrics.json")
    print(f"wrote {len(rec.metrics)} metrics to {RESULTS_DIR / 'metrics.json'}")
    from lorehaven import verify_findings   # local import: verify_findings imports this module
    verify_findings.main()


if __name__ == "__main__":
    main()
