"""projection.py: invalid inputs, accounting, direction checks and warnings.
Uses the committed outputs/results/metrics.json (no raw data needed)."""
import dataclasses
import math

import pytest

from lorehaven.projection import (BASE_PRICE, PODCAST_SEGMENTS, SEGMENT_NAME, TENURE_GROUPS, TESTED_BASES, InvalidPolicy,
                                  Policy, load_rates, project)


@pytest.fixture(scope="module")
def rates():
    return load_rates()


def policy(**changes):
    """The recommended policy with some settings changed."""
    base = Policy(offer_share={"high_podcast": 1.0, "low_podcast": 1.0}, prospect_discount={"high_podcast": 5, "low_podcast": 5},
                  new_member_discount=5, established_member_discount=1, win_back_offers=False)
    return dataclasses.replace(base, **changes)


@pytest.mark.parametrize("changes, field", [
    ({"prospect_discount": {"high_podcast": 6, "low_podcast": 5}}, "prospect_discount.high_podcast"),
    ({"prospect_discount": {"high_podcast": 2.5, "low_podcast": 5}}, "prospect_discount.high_podcast"),
    ({"offer_share": {"high_podcast": 1.0, "low_podcast": 1.5}}, "offer_share.low_podcast"),
    ({"offer_share": {"high_podcast": float("nan"), "low_podcast": 1.0}}, "offer_share.high_podcast"),
    ({"new_member_discount": 0}, "new_member_discount"),                 # members at full price were never observed
    ({"established_member_discount": 6}, "established_member_discount"),
    ({"horizon_quarters": 0}, "horizon_quarters"),
    ({"horizon_quarters": 41}, "horizon_quarters"),
    ({"discount_rate_per_quarter": 1.0}, "discount_rate_per_quarter"),
    ({"win_back_offers": "yes"}, "win_back_offers"),
    ({"holdout_list_share": 0.6}, "holdout_list_share"),
    ({"holdout_test_share": -0.1}, "holdout_test_share"),
    ({"base_price": 11}, "base_price"),                                   # never charged
    ({"base_price": 16}, "base_price"),
    ({"base_price": 12.5}, "base_price"),
])
def test_untested_or_invalid_inputs_raise_a_clear_error(rates, changes, field):
    with pytest.raises(InvalidPolicy) as error:
        project(policy(**changes), rates)
    assert error.value.field == field


def test_first_quarter_uses_the_table_rates_exactly(rates):
    """Quarter 1 revenue = starting prospects x share x sign-up rate at $5 off x $7, summed over the two segments."""
    share = {"high_podcast": rates.share_high_podcast, "low_podcast": 1 - rates.share_high_podcast}
    expected = sum(1000 * share[s] * rates.signup[BASE_PRICE, SEGMENT_NAME[s, "never"], 5] * (BASE_PRICE - 5) for s in PODCAST_SEGMENTS)
    assert project(policy(horizon_quarters=1), rates)["summary"]["first_quarter_revenue_per_1000"] == pytest.approx(expected)


def test_people_are_conserved(rates):
    """Members at the end + former members + never members = starting prospects, every quarter."""
    result = project(policy(horizon_quarters=8), rates)
    joined = sum(q["new_members"] for q in result["quarters"])
    churned = sum(q["churned"] for q in result["quarters"])
    assert result["quarters"][-1]["members"] == pytest.approx(joined - churned)


def test_per_thousand_results_do_not_depend_on_cohort_size(rates):
    small, large = (project(policy(starting_prospects=n), rates)["summary"] for n in (1000, 50000))
    for key in small:
        assert small[key] == pytest.approx(large[key])


def test_deeper_intro_offer_gives_more_first_quarter_members(rates):
    members = lambda off: project(policy(horizon_quarters=1, prospect_discount={s: off for s in PODCAST_SEGMENTS}), rates)["quarters"][0]["members"]
    assert members(0) < members(3) < members(5)


def test_deeper_member_discount_lowers_churn(rates):
    churn = lambda off: project(policy(new_member_discount=off, established_member_discount=off), rates)["summary"]["average_quarterly_churn"]
    assert churn(5) < churn(1)


def test_discounting_future_revenue_never_increases_it(rates):
    value = lambda d: project(policy(discount_rate_per_quarter=d), rates)["summary"]["revenue_per_1000_prospects"]
    assert value(0.03) < value(0.0)


def test_todays_random_depths_and_win_back_branch_run(rates):
    result = project(Policy(todays_random_depths=True, win_back_offers=False), rates)
    assert result["summary"]["revenue_per_1000_prospects"] > 0


def test_offer_share_above_what_was_tested_is_flagged(rates):
    assert project(policy(), rates)["warnings"]
    tested = {s: rates.tested_offer_share for s in PODCAST_SEGMENTS}
    assert not project(policy(offer_share=tested), rates)["warnings"]


def test_all_rates_are_shares_and_all_outputs_finite(rates):
    assert all(0 < r < 1 for r in list(rates.signup.values()) + list(rates.stay.values()))
    assert len(rates.stay) == len(TESTED_BASES) * len(PODCAST_SEGMENTS) * len(TENURE_GROUPS) * 5
    summary = project(policy(horizon_quarters=40), rates)["summary"]
    assert all(math.isfinite(v) for v in summary.values())


def test_tested_bases_use_their_own_table_and_in_between_bases_blend(rates):
    assert rates.signup_rate(15, "cold", 3) == rates.signup[15, "cold", 3]
    blended = rates.signup_rate(13, "cold", 3)
    assert blended == pytest.approx(2 / 3 * rates.signup[12, "cold", 3] + 1 / 3 * rates.signup[15, "cold", 3])
    assert rates.stay_rate(14, "high_podcast", "established", 1) == pytest.approx(
        1 / 3 * rates.stay[12, "high_podcast", "established", 1] + 2 / 3 * rates.stay[15, "high_podcast", "established", 1])


def test_revenue_uses_the_chosen_base_price(rates):
    first = lambda base: project(policy(base_price=base, horizon_quarters=1), rates)
    share = {"high_podcast": rates.share_high_podcast, "low_podcast": 1 - rates.share_high_podcast}
    expected = sum(1000 * share[s] * rates.signup[15, SEGMENT_NAME[s, "never"], 5] * (15 - 5) for s in PODCAST_SEGMENTS)
    assert first(15)["summary"]["first_quarter_revenue_per_1000"] == pytest.approx(expected)


def test_a_base_other_than_12_warns_that_it_compares_different_years(rates):
    assert not any("2017-18" in w for w in project(policy(offer_share={s: 0.25 for s in PODCAST_SEGMENTS}), rates)["warnings"])
    for base in (13, 15):
        assert any("2017-18" in w for w in project(policy(base_price=base), rates)["warnings"])
    assert any("blend" in w for w in project(policy(base_price=14), rates)["warnings"])


def test_holdout_is_the_share_weighted_sum_of_its_arms(rates):
    """85/10/5: the main policy on 85% of prospects + list price on 10% + $3 off on 5%."""
    revenue = lambda p: project(p, rates)["summary"]["revenue_per_1000_prospects"]
    arm = lambda share, off: policy(offer_share={s: share for s in PODCAST_SEGMENTS}, prospect_discount={s: off for s in PODCAST_SEGMENTS})
    expected = 0.85 * revenue(policy()) + 0.10 * revenue(arm(0.0, 0)) + 0.05 * revenue(arm(1.0, 3))
    assert revenue(policy(holdout_list_share=0.10, holdout_test_share=0.05)) == pytest.approx(expected)


def test_holdout_conserves_people(rates):
    result = project(policy(holdout_list_share=0.10, holdout_test_share=0.05, horizon_quarters=6), rates)
    joined = sum(q["new_members"] for q in result["quarters"])
    churned = sum(q["churned"] for q in result["quarters"])
    assert result["quarters"][-1]["members"] == pytest.approx(joined - churned)
