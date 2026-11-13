"""Backcast: replay 2017-2019 with the simulator's own quarter step and compare to actual member_count.

Model (pooled across podcast segments, one per status / tenure group):
  logit P = region FE + quarter FE + slope x price,   fit on the backcast's training quarters
Policy actually in force (not realized prices): Panem at $15 list, no discounts; elsewhere base $15
(-> $12 from quarter 9), 25% of prospects offered a random $1-$5 discount, members always a random $1-$5.

  in_sample      fit on quarters 0-11, replay 0-11 from launch (everyone a never-member prospect)
  out_of_sample  fit on quarters 0-7, forecast 8-11 from the ACTUAL end-of-2018 state, with two baselines:
                   same_season   2018 quarter effect of the same season (seasonal naive)
                   avg_2018      average of the four 2018 quarter effects
Error = predicted vs actual member_count by region x quarter (aggregate.csv).
"""
import numpy as np
import pandas as pd

from lorehaven import data_prep, models
from lorehaven.simulate import TENURE_GROUPS, PricingPolicy, SegmentModel, _advance_segment

POOLED = "high_podcast"   # one pooled segment; key name only matters to the price-mix helpers
STATUS_GROUPS = {"join_never": ("prospect", 0), "join_lapsed": ("prospect", 1)}


def _fit_backcast_models(table, quarters) -> dict:
    rows = table[table.quarter_index.isin(quarters)]
    fits = {}
    prospects = models.prospects(rows)
    fits["join_never"] = models.acquisition_model(prospects[prospects.is_lapsed == 0], fixed_effects=("region_name", "quarter_index"))
    fits["join_lapsed"] = models.acquisition_model(prospects[prospects.is_lapsed == 1], fixed_effects=("region_name", "quarter_index"))
    for group, (low, high) in models.TENURE_GROUPS.items():
        member_rows = models.members(rows)
        fits[f"stay_{group}"] = models.retention_model(member_rows[member_rows.member_tenure.between(low, high)],
                                                       fixed_effects=("region_name", "quarter_index"))
    return fits


def _intercept(fit, region, quarters) -> float:
    """Region FE (full set, prefix fe0_) + average quarter FE over `quarters` (reference quarter = 0)."""
    fe = fit["fixed_effects"]
    quarters = quarters if isinstance(quarters, (list, tuple, range)) else [quarters]
    return float(fe[region] + np.mean([fe.get(f"fe1_{q}", 0.0) for q in quarters]))


def _quarter_model(fits, region, effect_quarter) -> SegmentModel:
    values = {"share_of_prospects": 1.0}
    for part, fit in fits.items():
        values[f"{part}_intercept"] = _intercept(fit, region, effect_quarter)
        values[f"{part}_price_slope"] = fit["coef"]["price"]
    return SegmentModel(**values)


def _policy_in_force(region, quarter) -> PricingPolicy:
    if region == data_prep.CONTROL_REGION:
        return PricingPolicy(base_price=15, offer_share={s: 0.0 for s in ("high_podcast", "low_podcast")},
                             prospect_discount={s: 0.0 for s in ("high_podcast", "low_podcast")},
                             new_member_discount=0.0, established_member_discount=0.0)
    base = 12 if quarter >= data_prep.BASE_CUT_QUARTER_INDEX else 15
    return PricingPolicy(base_price=base, random_depths=True)


def _actual_state(table, region, quarter) -> dict:
    """Customer counts by status / tenure group at the START of `quarter` (i.e. after quarter - 1)."""
    rows = table[(table.region_name == region) & (table.quarter_index == quarter)]
    state = {"never": float((rows.status == "never_prospect").sum()), "lapsed": float((rows.status == "lapsed_prospect").sum())}
    for group, (low, high) in models.TENURE_GROUPS.items():
        state[group] = float(((rows.status == "member") & rows.member_tenure.between(low, high)).sum())
    return state


def _replay(table, fits, region, first_quarter, last_quarter, effect_quarter_of) -> list:
    if first_quarter == 0:
        state = {"never": float((table[(table.region_name == region) & (table.quarter_index == 0)]).shape[0]),
                 "lapsed": 0.0, **{g: 0.0 for g in TENURE_GROUPS}}
    else:
        state = _actual_state(table, region, first_quarter)
    predictions = []
    for quarter in range(first_quarter, last_quarter + 1):
        model = _quarter_model(fits, region, effect_quarter_of(quarter))
        _advance_segment(_policy_in_force(region, quarter), model, state, POOLED)
        predictions.append({"region_name": region, "quarter_index": quarter,
                            "predicted_members": sum(state[g] for g in TENURE_GROUPS)})
    return predictions


def run_backcast(table) -> dict:
    aggregate = data_prep.load_aggregate()[["region_name", "quarter_index", "member_count"]]
    regions = sorted(table.region_name.astype(str).unique())
    results = {}
    in_fits = _fit_backcast_models(table, range(0, 12))
    in_rows = [p for r in regions for p in _replay(table, in_fits, r, 0, 11, lambda q: q)]
    out_fits = _fit_backcast_models(table, range(0, 8))
    same_season = [p for r in regions for p in _replay(table, out_fits, r, 8, 11, lambda q: q - 4)]
    avg_2018 = [p for r in regions for p in _replay(table, out_fits, r, 8, 11, lambda q: range(4, 8))]
    for name, rows in (("in_sample", in_rows), ("out_of_sample_same_season", same_season), ("out_of_sample_avg_2018", avg_2018)):
        frame = pd.DataFrame(rows).merge(aggregate, on=["region_name", "quarter_index"])
        frame["abs_pct_error"] = (frame.predicted_members - frame.member_count).abs() / frame.member_count
        frame["is_treated_region"] = frame.region_name != data_prep.CONTROL_REGION
        results[name] = frame
    return results


def summarize(results: dict) -> dict:
    summary = {}
    for name, frame in results.items():
        summary[f"{name}.mape"] = frame.abs_pct_error.mean()
        summary[f"{name}.mape_treated"] = frame[frame.is_treated_region].abs_pct_error.mean()
        summary[f"{name}.mape_panem"] = frame[~frame.is_treated_region].abs_pct_error.mean()
        last = frame[frame.quarter_index == 11]
        summary[f"{name}.total_members_q11_predicted"] = last.predicted_members.sum()
        summary[f"{name}.total_members_q11_actual"] = last.member_count.sum()
        summary[f"{name}.total_error_q11_pct"] = last.predicted_members.sum() / last.member_count.sum() - 1
    return summary
