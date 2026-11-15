"""The decision layer: the policies we compare, what each earns, and how big the holdout must be.

Two ways to value a policy, both built on the observed rates:
  first_quarter_value   one quarter, straight from the randomized sign-up table (no projection needed)
  projection.project    several quarters, adding renewals (needed to compare member discounts)
"""
import math

import pandas as pd

from lorehaven.projection import PODCAST_SEGMENTS, Policy

HOLDOUT_ARMS = {"5_off": 0.85, "list": 0.10, "3_off": 0.05}   # recommended rollout: each prospect assigned once, kept
Z_95_TWO_SIDED, Z_80_POWER = 1.96, 0.84


# Inputs:  the sign-up table from rates.signup_by_segment_and_discount, and the projection
# Outputs: named policies, policy values and holdout sizes (returned); pipeline.py records them


def everyone(value) -> dict:
    """The same setting for both podcast segments."""
    return {segment: value for segment in PODCAST_SEGMENTS}


def named_policies() -> dict:
    """The policies compared in the write-up, the figures and the tool. $12 base unless named otherwise.
    Every '$5 off for new prospects' policy runs with the recommended holdout (85% $5 off / 10% list / 5% $3 off),
    so all quoted values are for the policy as it would actually run."""
    holdout = {"holdout_list_share": HOLDOUT_ARMS["list"], "holdout_test_share": HOLDOUT_ARMS["3_off"]}
    offer_5 = dict(offer_share=everyone(1.0), prospect_discount=everyone(5), win_back_offers=False, **holdout)
    policies = {
        "today": Policy(todays_random_depths=True),
        "recommended": Policy(**offer_5, new_member_discount=5, established_member_discount=1),
    }
    for off in range(1, 6):    # same intro discount and holdout, one discount for every member
        policies[f"offer_5_members_{off}_off"] = Policy(**offer_5, new_member_discount=off, established_member_discount=off)
    policies["recommended_with_win_back"] = Policy(**{**vars(policies["recommended"]), "win_back_offers": True})
    policies["full_rollout"] = Policy(**{**vars(policies["recommended"]), "holdout_list_share": 0.0, "holdout_test_share": 0.0})
    for base in (13, 14, 15):   # the recommended discounts at a higher base (rates blended or from the $15 era)
        policies[f"recommended_at_{base}"] = Policy(**{**vars(policies["recommended"]), "base_price": base})
    policies["today_at_15"] = Policy(todays_random_depths=True, base_price=15)
    return policies


def first_quarter_value(signup: pd.DataFrame, off_by_segment: dict) -> float:
    """First-quarter revenue per prospect if every prospect in a segment got that segment's discount.
      value = sum over segments of  share of prospects x sign-up rate at that discount x price paid
    Each rate comes from the randomly chosen group that actually got that discount, so it stands in for
    'everyone gets it'. (This is what inverse-propensity weighting computes; robustness/ confirms it.)"""
    cells = signup.set_index(["segment", "discount_depth"])
    return float(sum(cells.share_of_prospects[(s, off)] * cells.revenue_per_prospect[(s, off)]
                     for s, off in off_by_segment.items()))


def minimum_detectable_difference(rate_a, n_a, rate_b, n_b) -> float:
    """Smallest true difference between two rates a test would catch 80% of the time at 5% significance:
      2.80 x sqrt( p_a (1 - p_a) / n_a  +  p_b (1 - p_b) / n_b )
    Assumes independent people; repeat visitors make the real figure somewhat larger."""
    return (Z_95_TWO_SIDED + Z_80_POWER) * math.sqrt(rate_a * (1 - rate_a) / n_a + rate_b * (1 - rate_b) / n_b)


def holdout_power(prospects_per_quarter, list_rate, offer_rate, renewal_rate=0.5, quarters=1, list_share=None) -> dict:
    """Minimum detectable differences for the list-price arm vs the $5 arm after `quarters` quarters of traffic:
    sign-up rate among all prospects, and renewal rate among the people who joined (renewal_rate 0.5 = worst case)."""
    list_share = HOLDOUT_ARMS["list"] if list_share is None else list_share
    n_list = prospects_per_quarter * quarters * list_share
    n_offer = prospects_per_quarter * quarters * HOLDOUT_ARMS["5_off"]
    return {"list_arm_prospects": n_list,
            "signup": minimum_detectable_difference(list_rate, n_list, offer_rate, n_offer),
            "renewal": minimum_detectable_difference(renewal_rate, n_list * list_rate, renewal_rate, n_offer * offer_rate)}
