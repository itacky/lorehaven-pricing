"""rates.py on a tiny hand-made table: each rate is a plain average, segments and tenure groups are labelled right."""
import pandas as pd
import pytest

from lorehaven import rates


def row(**changes):
    """One customer-quarter row in the discounting regions, $12 era, as a never-member, engaged listener."""
    base = dict(customer_id=1, quarter_index=9, is_treated_region=1, is_prospect=1, is_lapsed=0, is_high_podcast=1,
                status="never_prospect", member_tenure=0, discount_depth=0, discount_flag=0, base_price=12,
                membership_price=12, sign_up_flag=0, stayed=1)
    return {**base, **changes}


def test_signup_rate_is_the_plain_average_per_segment_and_discount():
    table = pd.DataFrame([row(sign_up_flag=1), row(), row(), row(),                       # list price: 1 of 4 join
                          row(discount_depth=5, discount_flag=1, membership_price=7, sign_up_flag=1),
                          row(discount_depth=5, discount_flag=1, membership_price=7)])     # $5 off: 1 of 2 join
    cells = rates.signup_by_segment_and_discount(table).set_index("discount_depth")
    assert cells.loc[0, "rate"] == pytest.approx(0.25) and cells.loc[0, "n"] == 4
    assert cells.loc[5, "rate"] == pytest.approx(0.5)
    assert cells.loc[5, "uplift"] == pytest.approx(0.25)                 # 50% - 25%
    assert cells.loc[5, "incremental_share"] == pytest.approx(0.5)       # 25 of every 50 joiners needed the offer
    assert cells.loc[5, "revenue_per_prospect"] == pytest.approx(0.5 * 7)
    assert set(cells.segment) == {"warm_listener"}


def test_other_eras_and_panem_are_left_out_of_the_current_era():
    table = pd.DataFrame([row(sign_up_flag=1), row(quarter_index=8), row(is_treated_region=0)])
    assert rates.signup_by_segment_and_discount(table).n.sum() == 1


@pytest.mark.parametrize("lapsed, podcast, name", [(0, 1, "warm_listener"), (0, 0, "cold"), (1, 1, "win_back"),
                                                   (1, 0, "lapsed_low_podcast")])
def test_prospect_segments(lapsed, podcast, name):
    table = pd.DataFrame([row(is_lapsed=lapsed, is_high_podcast=podcast)])
    assert rates.prospects(table).segment.iloc[0] == name


@pytest.mark.parametrize("tenure, group", [(1, "first_renewal"), (2, "second_renewal"), (3, "established"), (9, "established")])
def test_tenure_groups(tenure, group):
    table = pd.DataFrame([row(status="member", is_prospect=0, member_tenure=tenure)])
    assert rates.members(table).tenure_group.iloc[0] == group


def test_stay_rate_by_tenure_and_price():
    member = dict(status="member", is_prospect=0, member_tenure=1, membership_price=11)
    table = pd.DataFrame([row(**member, stayed=1), row(**member, stayed=0), row(**member, stayed=1)])
    cell = rates.stay_by_tenure_and_price(table).iloc[0]
    assert (cell.segment, cell.tenure_group, cell.membership_price, cell.n) == ("high_podcast", "first_renewal", 11, 3)
    assert cell.rate == pytest.approx(2 / 3)


def test_base_cut_gap_change_is_a_difference_of_differences():
    two_by_two = pd.DataFrame({"group": ["cut_regions", "panem", "cut_regions", "panem"],
                               "period": ["before", "before", "after", "after"], "rate": [0.03, 0.05, 0.06, 0.04]})
    assert rates.gap_change(two_by_two, "before", "after") == pytest.approx((0.06 - 0.04) - (0.03 - 0.05))


def test_standard_error():
    assert rates.standard_error(0.5, 100) == pytest.approx(0.05)
