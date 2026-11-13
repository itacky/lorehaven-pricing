"""Unit tests for lorehaven.simulate: invalid inputs, edge cases, accounting, monotonicity, warnings.
Uses the committed outputs/results/metrics.json (no raw data needed)."""
import dataclasses
import math

import pytest

from lorehaven.simulate import (SEGMENTS, TENURE_GROUPS, InvalidPolicy, PricingPolicy, load_model,
                                member_value, simulate)

EVERYONE = lambda value: {s: value for s in SEGMENTS}


@pytest.fixture(scope="module")
def model():
    return load_model()


def policy(**changes):
    base = PricingPolicy(base_price=12, offer_share=EVERYONE(1.0), prospect_discount=EVERYONE(5.0),
                         new_member_discount=5.0, established_member_discount=1.0, lapsed_get_offers=False)
    return dataclasses.replace(base, **changes)


# ---------------------------------------------------------------- invalid inputs
@pytest.mark.parametrize("changes, field", [
    ({"base_price": "12"}, "base_price"),
    ({"base_price": True}, "base_price"),
    ({"base_price": float("nan")}, "base_price"),
    ({"base_price": 0.5}, "base_price"),
    ({"offer_share": {"high_podcast": 1.2, "low_podcast": 0.5}}, "offer_share.high_podcast"),
    ({"offer_share": {"high_podcast": 0.5}}, "offer_share"),
    ({"prospect_discount": {"high_podcast": 12.0, "low_podcast": 1.0}}, "prospect_discount.high_podcast"),
    ({"prospect_discount": {"high_podcast": -1.0, "low_podcast": 1.0}}, "prospect_discount.high_podcast"),
    ({"new_member_discount": 13.0}, "new_member_discount"),
    ({"established_member_discount": -0.5}, "established_member_discount"),
    ({"horizon_quarters": 0}, "horizon_quarters"),
    ({"horizon_quarters": 41}, "horizon_quarters"),
    ({"horizon_quarters": True}, "horizon_quarters"),
    ({"horizon_quarters": 12.0}, "horizon_quarters"),
    ({"starting_prospects": 0}, "starting_prospects"),
    ({"discount_rate_per_quarter": 1.0}, "discount_rate_per_quarter"),
    ({"lapsed_get_offers": "yes"}, "lapsed_get_offers"),
    ({"random_depths": True, "base_price": 5.0, "prospect_discount": {"high_podcast": 1.0, "low_podcast": 1.0},
      "new_member_discount": 1.0, "established_member_discount": 1.0}, "base_price"),
])
def test_invalid_inputs_raise_clear_error(model, changes, field):
    with pytest.raises(InvalidPolicy) as error:
        simulate(policy(**changes), model)
    assert error.value.field == field
    assert len(str(error.value)) > 20          # a sentence, not a code


# ---------------------------------------------------------------- edge cases and accounting
def test_one_quarter_horizon(model):
    result = simulate(policy(horizon_quarters=1), model)
    assert len(result["quarters"]) == 1
    assert result["kpis"]["ltv_per_1000_prospects"] == pytest.approx(result["kpis"]["first_quarter_revenue_per_1000"])


def test_no_discounts_means_no_discount_cost(model):
    result = simulate(policy(offer_share=EVERYONE(0.0), prospect_discount=EVERYONE(0.0),
                             new_member_discount=0.0, established_member_discount=0.0), model)
    assert result["kpis"]["discount_cost_per_1000"] == 0
    assert result["kpis"]["share_of_member_quarters_discounted"] == 0


def test_per_thousand_results_do_not_depend_on_cohort_size(model):
    small = simulate(policy(starting_prospects=500), model)["kpis"]
    large = simulate(policy(starting_prospects=20000), model)["kpis"]
    for key in small:
        assert small[key] == pytest.approx(large[key])


def test_people_are_conserved(model):
    result = simulate(policy(lapsed_get_offers=True, horizon_quarters=20), model)
    joined = churned = 0.0
    for quarter in result["quarters"]:
        joined += quarter["new_members"]
        churned += quarter["churned"]
        assert quarter["members"] == pytest.approx(joined - churned)
        assert 0 <= quarter["members"] <= 1000


def test_revenue_equals_payers_times_prices_bounds(model):
    result = simulate(policy(), model)
    for quarter in result["quarters"]:
        assert quarter["revenue"] <= 12 * quarter["members"] + 1e-9   # nobody pays more than the base price
        assert quarter["revenue"] >= 7 * quarter["members"] - 1e-9    # lowest price in this policy is $7


def test_discounting_future_revenue_never_increases_ltv(model):
    plain = simulate(policy(), model)["kpis"]["ltv_per_1000_prospects"]
    discounted = simulate(policy(discount_rate_per_quarter=0.03), model)["kpis"]["ltv_per_1000_prospects"]
    assert discounted < plain


def test_random_depths_with_no_winback_branch(model):
    result = simulate(policy(random_depths=True, lapsed_get_offers=False, offer_share=EVERYONE(0.25)), model)
    assert result["kpis"]["ltv_per_1000_prospects"] > 0


def test_segment_specific_settings_are_used(model):
    high_only = simulate(policy(offer_share={"high_podcast": 1.0, "low_podcast": 0.0}), model)["kpis"]
    low_only = simulate(policy(offer_share={"high_podcast": 0.0, "low_podcast": 1.0}), model)["kpis"]
    assert high_only["first_quarter_revenue_per_1000"] != pytest.approx(low_only["first_quarter_revenue_per_1000"])


def test_partial_offer_share_without_random_depths(model):
    half = simulate(policy(offer_share=EVERYONE(0.5)), model)["kpis"]["first_quarter_revenue_per_1000"]
    none = simulate(policy(offer_share=EVERYONE(0.0)), model)["kpis"]["first_quarter_revenue_per_1000"]
    full = simulate(policy(offer_share=EVERYONE(1.0)), model)["kpis"]["first_quarter_revenue_per_1000"]
    assert min(none, full) < half < max(none, full)


# ---------------------------------------------------------------- monotonicity
def test_deeper_prospect_discount_gives_more_first_quarter_signups(model):
    signups = [simulate(policy(prospect_discount=EVERYONE(float(d)), horizon_quarters=1), model)["quarters"][0]["new_members"]
               for d in range(0, 6)]
    assert signups == sorted(signups) and signups[0] < signups[-1]


def test_wider_offer_reach_gives_more_signups(model):
    signups = [simulate(policy(offer_share=EVERYONE(share), horizon_quarters=1), model)["quarters"][0]["new_members"]
               for share in (0.0, 0.25, 0.5, 1.0)]
    assert signups == sorted(signups)


def test_deeper_member_discount_lowers_churn(model):
    churn = [simulate(policy(new_member_discount=float(d), established_member_discount=float(d)), model)["kpis"]["average_quarterly_churn"]
             for d in range(1, 6)]
    assert churn == sorted(churn, reverse=True)


def test_stay_probability_falls_with_price(model):
    for segment in model.segments.values():
        for group in TENURE_GROUPS:
            assert segment.stay_probability(group, 7) > segment.stay_probability(group, 11)


def test_member_value_steady_state_exceeds_finite_horizon(model):
    segment = model.segments["high_podcast"]
    assert member_value(segment, 10, 12) < member_value(segment, 10, 40) < member_value(segment, 10, None)


# ---------------------------------------------------------------- warnings
def test_recommended_prices_are_inside_tested_range(model):
    warnings = simulate(policy(), model)["warnings"]
    assert len(warnings) == 1 and "Offers reached" in warnings[0]       # only the offer-coverage caveat


def test_offer_coverage_at_tested_share_has_no_warning(model):
    share = model.tested_offer_share
    assert simulate(policy(offer_share=EVERYONE(share)), model)["warnings"] == []


def test_other_base_price_is_flagged(model):
    warnings = simulate(policy(base_price=15), model)["warnings"]
    assert any("calibrated" in w for w in warnings)


def test_members_at_full_price_are_flagged(model):
    warnings = simulate(policy(new_member_discount=0.0), model)["warnings"]
    assert any("never observed" in w for w in warnings)


def test_prices_below_tested_range_are_flagged(model):
    warnings = simulate(policy(prospect_discount=EVERYONE(8.0)), model)["warnings"]
    assert any("outside the tested" in w for w in warnings)


def test_all_outputs_are_finite(model):
    result = simulate(policy(horizon_quarters=40), model)
    assert all(math.isfinite(v) for v in result["kpis"].values())
