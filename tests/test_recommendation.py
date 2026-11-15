"""recommendation.py and formatting.py: the named policies are valid, the value and power formulas are right."""
import math

import pandas as pd
import pytest

from lorehaven.formatting import percents_summing_to_100
from lorehaven.projection import load_rates, project
from lorehaven.recommendation import (HOLDOUT_ARMS, first_quarter_value, holdout_power, minimum_detectable_difference,
                                      named_policies)


def test_every_named_policy_projects_without_error():
    rates = load_rates()
    for name, policy in named_policies().items():
        assert project(policy, rates)["summary"]["revenue_per_1000_prospects"] > 0, name


def test_holdout_arms_add_up_to_everyone():
    assert sum(HOLDOUT_ARMS.values()) == pytest.approx(1.0)


def test_first_quarter_value_is_a_share_weighted_average():
    table = pd.DataFrame({"segment": ["a", "b"], "discount_depth": [5, 5], "share_of_prospects": [0.25, 0.75],
                          "revenue_per_prospect": [4.0, 2.0]})
    assert first_quarter_value(table, {"a": 5, "b": 5}) == pytest.approx(0.25 * 4 + 0.75 * 2)


def test_minimum_detectable_difference_formula():
    expected = 2.80 * math.sqrt(0.5 * 0.5 / 1000 + 0.5 * 0.5 / 1000)
    assert minimum_detectable_difference(0.5, 1000, 0.5, 1000) == pytest.approx(expected)


def test_more_traffic_or_a_bigger_holdout_detects_smaller_differences():
    small = holdout_power(100_000, 0.06, 0.25, quarters=1, list_share=0.05)
    assert holdout_power(100_000, 0.06, 0.25, quarters=3, list_share=0.05)["renewal"] < small["renewal"]
    assert holdout_power(100_000, 0.06, 0.25, quarters=1, list_share=0.10)["renewal"] < small["renewal"]


def test_percents_summing_to_100_uses_largest_remainders():
    shares = {"warm": 0.2077, "cold": 0.6467, "win_back": 0.1284, "former": 0.0172}   # naive rounding gives 101
    assert percents_summing_to_100(shares) == {"warm": 21, "cold": 64, "win_back": 13, "former": 2}
    assert sum(percents_summing_to_100({"a": 1, "b": 1, "c": 1}).values()) == 100
