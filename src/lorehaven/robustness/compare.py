"""Set the simple pipeline's answers beside the model-based appendix's answers to the same questions.

Usage:  python -m lorehaven.robustness.compare   (after both pipelines have run; no raw data needed)
Writes  outputs/robustness/simple_vs_advanced.csv  one row per question
        outputs/robustness/crosscheck.json         summary counts quoted in the write-up
"""
import json

import pandas as pd

from lorehaven.data_prep import REPO_ROOT
from lorehaven.projection import Policy, load_rates, project
from lorehaven.recommendation import named_policies

SIMPLE = REPO_ROOT / "outputs" / "results" / "metrics.json"
ADVANCED = REPO_ROOT / "outputs" / "robustness" / "metrics.json"
OUT_DIR = REPO_ROOT / "outputs" / "robustness"
SEGMENTS = ("warm_listener", "cold", "win_back", "lapsed_low_podcast")


# Inputs:  outputs/results/metrics.json (simple) and outputs/robustness/metrics.json (advanced)
# Outputs: simple_vs_advanced.csv and crosscheck.json in outputs/robustness/


def odds_change_per_dollar(rate_high_price, rate_low_price, dollars):
    """Average change in the odds of signing up per $1 off, from two observed rates: (odds ratio)^(1/dollars) - 1."""
    odds = lambda p: p / (1 - p)
    return (odds(rate_low_price) / odds(rate_high_price)) ** (1 / dollars) - 1


def tenure_vs_best_single_without_holdout() -> float:
    """Tenure discounts vs the best single member discount, all with a full $5 rollout (no holdout), as the
    advanced simulator measured it, so the two methods are compared like for like."""
    rates = load_rates(SIMPLE)
    no_holdout = lambda policy: Policy(**{**vars(policy), "holdout_list_share": 0.0, "holdout_test_share": 0.0})
    revenue = lambda policy: project(no_holdout(policy), rates)["summary"]["revenue_per_1000_prospects"]
    policies = named_policies()
    best_single = max(revenue(policies[f"offer_5_members_{off}_off"]) for off in range(1, 6))
    return revenue(policies["recommended"]) / best_single - 1


def comparison_rows(simple: dict, advanced: dict) -> list:
    """(question, simple method, simple answer, advanced method, advanced answer) for each shared question."""
    s = lambda key: simple[key]["value"]
    a = lambda key: advanced[key]["value"]
    rows = [
        ("Sign-up odds change per $1 off ($12 era)", "two observed rates, $12 vs $7",
         odds_change_per_dollar(s("rates.by_price.signup.base12.price12"), s("rates.by_price.signup.base12.price7"), 5),
         "logit, region x quarter fixed effects, all eras", a("headline.signup_odds_change_per_dollar_off")),
        ("First-quarter revenue per prospect, today", "observed average", s("first_quarter.today"),
         "on-policy mean, clustered SE", a("ope.status_quo_random_25pct.first_quarter_revenue")),
        ("First-quarter revenue per prospect, $5 to everyone", "weighted average of the $5 groups",
         s("first_quarter.everyone_5_off"), "inverse-propensity weighting", a("ope.offer_all_5_off.first_quarter_revenue")),
    ]
    for segment in SEGMENTS:
        rows.append((f"Sign-up uplift at $5 off: {segment}", "difference of two group averages", s(f"segment.{segment}.uplift_at_5"),
                     "linear model, region x quarter fixed effects", a(f"uplift.base12.{segment}.uplift_5")))
    rows += [
        ("2019 base cut raised list-price sign-ups (sign)", "cut regions minus Panem, 2018 vs 2019, points",
         s("base_cut.change_vs_panem"), "logit difference-in-differences", a("did.delta")),
        ("Full $5 rollout (no holdout) vs today, 3 years", "lookup-table projection", s("headline.full_rollout_vs_today"),
         "fitted-curve simulator", a("headline.ltv_recommended_vs_today_pct")),
        ("Full $5 rollout (no holdout) vs today, 10 years", "lookup-table projection", s("headline.full_rollout_vs_today_h40"),
         "fitted-curve simulator", a("headline.ltv_recommended_vs_today_pct_h40")),
        ("Recommended (85/10/5 holdout) vs today, 3 years", "lookup-table projection", s("headline.recommended_vs_today"),
         "fitted-curve simulator", a("headline.holdout_design_ltv_vs_today_pct")),
        ("Tenure discounts vs best single member discount (no holdout)", "lookup-table projection", tenure_vs_best_single_without_holdout(),
         "fitted-curve simulator", a("headline.ltv_recommended_vs_best_uniform_pct")),
    ]
    return rows


def main():
    """Compare, save the table and the summary counts."""
    simple, advanced = json.loads(SIMPLE.read_text()), json.loads(ADVANCED.read_text())
    table = pd.DataFrame(comparison_rows(simple, advanced),
                         columns=["question", "simple_method", "simple", "advanced_method", "advanced"])
    table["same_direction"] = (table.simple > 0) == (table.advanced > 0)
    # The base-cut row compares signs only (points vs log-odds), so it has no meaningful size gap.
    table["relative_gap"] = (table.simple - table.advanced).abs() / table.advanced.abs()
    table.loc[table.question.str.startswith("2019 base cut"), "relative_gap"] = float("nan")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT_DIR / "simple_vs_advanced.csv", index=False)
    summary = {"crosscheck.questions": len(table), "crosscheck.same_direction": int(table.same_direction.sum()),
               "crosscheck.largest_relative_gap": float(table.relative_gap.max())}
    (OUT_DIR / "crosscheck.json").write_text(json.dumps(
        {key: {"value": value, "unit": "", "label": "estimate", "note": "simple vs advanced, see simple_vs_advanced.csv"}
         for key, value in summary.items()}, indent=1))
    print(table[["question", "simple", "advanced", "same_direction"]].round(3).to_string(index=False))
    print(summary)


if __name__ == "__main__":
    main()
