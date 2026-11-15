"""Run the analysis and write outputs/results/metrics.json, the single source of truth.

Usage:  python -m lorehaven.pipeline                 full run from the raw CSVs
        python -m lorehaven.pipeline --derived-only  re-run projections and headline numbers from metrics.json
                                                     (no raw data needed)
Every number is saved with a label: observed (counted in the data), estimate (computed from observed numbers under a
stated assumption) or assumption (a choice we made). The write-up, figures and tool read only this file.
"""
import json
from pathlib import Path

import numpy as np

from lorehaven import data_prep, rates
from lorehaven.projection import Policy, load_rates, project
from lorehaven.recommendation import HOLDOUT_ARMS, first_quarter_value, holdout_power, named_policies

RESULTS_DIR = data_prep.REPO_ROOT / "outputs" / "results"
METRICS_PATH = RESULTS_DIR / "metrics.json"
HORIZONS = (12, 40)   # quarters: 3 years (headline) and 10 years (sensitivity)


# Inputs:  raw CSVs via data_prep (full run), or the existing metrics.json (--derived-only)
# Outputs: outputs/results/metrics.json and the rate tables as CSVs in outputs/results/


class MetricsRecorder:
    def __init__(self, metrics=None):
        """Start from an empty (or existing) metrics dictionary."""
        self.metrics = metrics or {}

    def add(self, key, value, unit, label, note=""):
        """Record one number with its unit, its label (observed / estimate / assumption) and a note."""
        if isinstance(value, (np.floating, np.integer, np.bool_)):
            value = value.item()
        if label not in ("observed", "estimate", "assumption"):
            raise ValueError(f"bad label {label}")
        self.metrics[key] = {"value": value, "unit": unit, "label": label, "note": note}

    def value(self, key):
        """Read back a recorded number."""
        return self.metrics[key]["value"]

    def save(self, path: Path = METRICS_PATH):
        """Write all metrics to JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.metrics, indent=1, sort_keys=True))


def record_assumptions(rec, table):
    """The choices the analysis rests on, and the size of the data."""
    rec.add("assumption.season_order", "winter->spring->summer->fall", "", "assumption", "No date field in the data")
    rec.add("assumption.launch_quarter", "2017 winter; no members before", "", "assumption", "Member counts at q0 = sign-ups")
    rec.add("assumption.podcast_cutoff", data_prep.PODCAST_SEGMENT_CUTOFF, "score", "assumption",
            "Podcast score >= 0.5 = engaged listener")
    rec.add("assumption.offers_random", "who got an offer is as good as random", "", "assumption",
            "Brief says business rules decide eligibility, but no observable predicts it (A2)")
    for arm, share in HOLDOUT_ARMS.items():
        rec.add(f"assumption.holdout_arm_share.{arm}", share, "share of new prospects", "assumption",
                "Recommended rollout: each prospect assigned once and kept")
    rec.add("data.customers", table.customer_id.nunique(), "customers", "observed")
    rec.add("data.panel_rows", len(table), "customer-quarters", "observed")


def record_price_tables(rec, table):
    """Sign-up and stay rates at every price, in both base-price eras: the plainest view of price response."""
    for outcome, frame in (("signup", rates.signup_by_price(table)), ("stay", rates.stay_by_price(table))):
        frame.to_csv(RESULTS_DIR / f"{outcome}_by_price.csv", index=False)
        for r in frame.itertuples():
            rec.add(f"rates.by_price.{outcome}.base{r.base_price}.price{r.membership_price}", r.rate, "share", "observed",
                    f"n={r.n}; discounting regions, quarters 1-11")


def record_signup_table(rec, table):
    """$12 era: sign-up rate by prospect segment and discount, and what the offer adds in each segment."""
    signup = rates.signup_by_segment_and_discount(table)
    signup.to_csv(RESULTS_DIR / "signup_by_segment_and_discount.csv", index=False)
    for r in signup.itertuples():
        rec.add(f"rates.signup.{r.segment}.off{r.discount_depth}", r.rate, "share", "observed", f"n={r.n}; $12 era")
        rec.add(f"rates.signup.{r.segment}.off{r.discount_depth}.n", r.n, "prospect-quarters", "observed")
    for segment, rows in signup.groupby("segment"):
        at5 = rows.set_index("discount_depth").loc[5]
        rec.add(f"segment.{segment}.share_of_prospects", at5.share_of_prospects, "share", "observed", "$12 era")
        rec.add(f"segment.{segment}.uplift_at_5", at5.uplift, "share", "observed",
                "Sign-up rate at $5 off minus at list price (randomized groups)")
        rec.add(f"segment.{segment}.incremental_share_at_5", at5.incremental_share, "share", "estimate",
                "Share of $5-offer joiners who would not have joined at list. ASSUMES nobody is put off by an offer")
        best = rows.loc[rows.revenue_per_prospect.idxmax()]
        rec.add(f"segment.{segment}.best_first_quarter_discount", int(best.discount_depth), "$ off", "observed",
                "Discount with the highest first-quarter revenue per prospect ($0-$5 tested)")
    return signup


def record_stay_table(rec, table):
    """$12 era: share of members who stay, by podcast segment, tenure and price."""
    stay = rates.stay_by_tenure_and_price(table)
    stay.to_csv(RESULTS_DIR / "stay_by_tenure_and_price.csv", index=False)
    for r in stay.itertuples():
        rec.add(f"rates.stay.{r.segment}.{r.tenure_group}.price{r.membership_price}", r.rate, "share", "observed",
                f"n={r.n}; $12 era")


def record_first_quarter_values(rec, table, signup):
    """One-quarter revenue per prospect: today (observed) vs giving every prospect the same offer."""
    era_prospects = rates.prospects(rates.discounting_regions(table, rates.CURRENT_ERA_QUARTERS))
    rec.add("first_quarter.today", float((era_prospects.sign_up_flag * era_prospects.membership_price).mean()),
            "$ per prospect", "observed", "Today's policy as it ran: random 25% offers of $1-$5, $12 era")
    segments = list(rates.PROSPECT_SEGMENTS.values())
    for off in (0, 3, 5):
        rec.add(f"first_quarter.everyone_{off}_off", first_quarter_value(signup, {s: off for s in segments}),
                "$ per prospect", "estimate", "Weighted average of the randomized group that got this offer")
    best = {s: rec.value(f"segment.{s}.best_first_quarter_discount") for s in segments}
    rec.add("first_quarter.best_discount_per_segment", first_quarter_value(signup, best), "$ per prospect", "estimate",
            f"Each segment at its best discount: {best}")


def record_base_cut(rec, table):
    """The 2019 cut from $15 to $12: list-price sign-up in the cut regions vs Panem (no randomization here)."""
    two_by_two = rates.base_cut_two_by_two(table)
    two_by_two.to_csv(RESULTS_DIR / "base_cut_two_by_two.csv", index=False)
    by_quarter = rates.base_cut_gap_by_quarter(table)
    by_quarter.to_csv(RESULTS_DIR / "base_cut_gap_by_quarter.csv", index=False)
    note = "List-price sign-up, cut regions minus Panem, in rate points. DIRECTION ONLY: one comparison region"
    rec.add("base_cut.change_vs_panem", rates.gap_change(two_by_two, "2018_spring_fall", "2019_spring_fall"), "points",
            "estimate", note + "; 2018 vs 2019 spring-fall")
    before, after = by_quarter[~by_quarter.after_cut], by_quarter[by_quarter.after_cut]
    for name, rows in (("before", before), ("after", after)):
        rec.add(f"base_cut.gap_{name}_min", rows.gap.min(), "points", "observed", note)
        rec.add(f"base_cut.gap_{name}_max", rows.gap.max(), "points", "observed", note)
        rec.add(f"base_cut.quarters_{name}", len(rows), "quarters", "observed")
        rec.add(f"base_cut.quarters_{name}_above_panem", int((rows.gap > 0).sum()), "quarters", "observed")
    price = lambda base, paid: rec.value(f"rates.by_price.signup.base{base}.price{paid}")
    rec.add("base_cut.list_rate_2019_at_12", price(12, 12), "share", "observed", "$12 list price, $12 era")
    rec.add("base_cut.offer_rate_2018_at_12", price(15, 12), "share", "observed", "$3 off a $15 list price, $15 era")


def record_projection_inputs(rec, table):
    """Starting mix and tested offer share, which the projection reads alongside the rate tables."""
    era = rates.discounting_regions(table, rates.CURRENT_ERA_QUARTERS)
    rec.add("projection.share_high_podcast", rates.never_member_share_high_podcast(table), "share", "observed",
            "Engaged listeners' share of never-member prospects, $12 era")
    rec.add("projection.tested_offer_share", float(era[era.is_prospect == 1].discount_flag.mean()), "share", "observed",
            "Share of prospects who got an offer, $12 era")
    rec.add("holdout.prospects_per_quarter", rates.prospects_per_quarter(table), "prospect-quarters", "observed",
            "Average per quarter, discounting regions, $12 era")


def record_projections(rec):
    """Project every named policy at 3 and 10 years from the rate tables just saved."""
    model_rates = load_rates(METRICS_PATH)
    for name, policy in named_policies().items():
        for horizon in HORIZONS:
            result = project(Policy(**{**vars(policy), "horizon_quarters": horizon}), model_rates)
            for kpi, value in result["summary"].items():
                if horizon == 12 or kpi == "revenue_per_1000_prospects":
                    suffix = "" if horizon == 12 else f".h{horizon}"
                    rec.add(f"policy.{name}{suffix}.{kpi}", value, "see note", "estimate",
                            f"{horizon} quarters, $12-era rates. " + " ".join(result["warnings"]))


def record_headlines(rec):
    """Ratios and holdout numbers quoted in the write-up, computed here so every quoted number is a metrics.json key."""
    revenue = lambda name, h="": rec.value(f"policy.{name}{h}.revenue_per_1000_prospects")
    best_single = max((f"offer_5_members_{off}_off" for off in range(1, 6)), key=revenue)
    rec.add("headline.best_single_member_discount", int(best_single.split("_")[3]), "$ off", "estimate")
    for h, label in (("", "3 years"), (".h40", "10 years")):
        tag = h.replace(".", "_")
        rec.add(f"headline.recommended_vs_today{tag}", revenue("recommended", h) / revenue("today", h) - 1, "share",
                "estimate", f"{label}; full rollout (every new prospect gets $5 off)")
        rollout = sum(share * revenue(f"holdout_arm_{arm}", h) for arm, share in HOLDOUT_ARMS.items())
        rec.add(f"headline.rollout_revenue_per_1000{tag}", rollout, "$ per 1,000 prospects", "estimate",
                f"{label}; 85% $5 / 10% list / 5% $3, each arm kept for life")
        rec.add(f"headline.rollout_vs_today{tag}", rollout / revenue("today", h) - 1, "share", "estimate", label)
    rec.add("headline.recommended_vs_best_single", revenue("recommended") / revenue(best_single) - 1, "share", "estimate",
            "Tenure discounts vs the best single discount for every member, 3 years")
    rec.add("headline.recommended_with_win_back_vs_today", revenue("recommended_with_win_back") / revenue("today") - 1,
            "share", "estimate", "Recommended plus offers to former members, 3 years")
    rec.add("headline.first_quarter_everyone_5_vs_today", rec.value("first_quarter.everyone_5_off") / rec.value("first_quarter.today") - 1,
            "share", "estimate")
    gain = rec.value("first_quarter.everyone_5_off") - rec.value("first_quarter.everyone_0_off")
    rec.add("holdout.cost_per_prospect_quarter", HOLDOUT_ARMS["list"] * gain, "$ per prospect", "estimate",
            "10% of prospects at list forgo the first-quarter gain of a $5 offer")
    traffic = rec.value("holdout.prospects_per_quarter")
    list_rate = rec.value("rates.by_price.signup.base12.price12")
    offer_rate = rec.value("rates.by_price.signup.base12.price7")
    rec.add("holdout.signup_gap_list_vs_5_off", offer_rate - list_rate, "points", "observed",
            "Sign-up rate at $5 off minus at list price, $12 era: the difference the holdout must see")
    for share, tag in ((0.10, "list10"), (0.05, "list5")):
        for quarters in (1, 3):
            power = holdout_power(traffic, list_rate, offer_rate, quarters=quarters, list_share=share)
            for measure in ("signup", "renewal"):
                rec.add(f"holdout.mde_{measure}_{tag}_q{quarters}", power[measure], "points", "estimate",
                        f"Smallest list-vs-$5 difference caught 80% of the time at 5% significance after {quarters} quarter(s)")


def main():
    """Full run from the raw data."""
    rec = MetricsRecorder()
    # 1. Load the raw CSVs into one customer x quarter table (status, tenure, prices; known data gaps set to missing)
    table = data_prep.build_analysis_table()
    # 2. Record the assumptions the analysis rests on
    record_assumptions(rec, table)
    # 3. EVIDENCE: sign-up and stay rates at every price, both eras (randomized prices, so averages are causal)
    record_price_tables(rec, table)
    # 4. EVIDENCE: $12 era sign-up by segment and discount: who the offer wins
    signup = record_signup_table(rec, table)
    # 5. EVIDENCE: $12 era stay rates by tenure and price: who is price-sensitive once they are members
    record_stay_table(rec, table)
    # 6. One-quarter value of each offer policy, straight from the sign-up table
    record_first_quarter_values(rec, table, signup)
    # 7. The 2019 base cut vs Panem (direction only)
    record_base_cut(rec, table)
    # 8. Projection inputs, then save so the projection can read the tables
    record_projection_inputs(rec, table)
    rec.save()
    # 9. Project each named policy 3 and 10 years ahead
    record_projections(rec)
    # 10. Headline ratios, rollout value and holdout power
    record_headlines(rec)
    rec.save()
    print(f"wrote {len(rec.metrics)} numbers to {METRICS_PATH}")


def refresh_derived():
    """Re-run projections and headlines from the saved rate tables (no raw data needed)."""
    rec = MetricsRecorder(json.loads(METRICS_PATH.read_text()))
    record_projections(rec)
    record_headlines(rec)
    rec.save()
    print(f"refreshed projections and headlines; {len(rec.metrics)} numbers in {METRICS_PATH}")


if __name__ == "__main__":
    import sys
    refresh_derived() if "--derived-only" in sys.argv else main()
