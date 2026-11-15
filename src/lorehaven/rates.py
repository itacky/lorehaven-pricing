"""The evidence: observed sign-up and stay rates, each a plain group average with its count.

Why averages are enough: Lorehaven re-priced customers by a random draw. Inside the discounting regions, whether a
prospect got an offer (25%) and how deep it was ($1-$5, equal shares) were randomized, so the groups at each price
are alike in everything except price. The difference between two group averages IS the effect of the price
difference. (A regression would only smooth these averages; lorehaven/robustness/ shows it gives the same answers.)

Two samples, named once here:
  ALL_ERAS     discounting regions, every quarter after launch (quarters 1-11): the price-response tables
  CURRENT_ERA  discounting regions at the $12 base (2019 spring-fall, quarters 9-11): what the projection uses
"""
import numpy as np
import pandas as pd

CURRENT_ERA_QUARTERS = (9, 10, 11)
TENURE_GROUPS = {"first_renewal": (1, 1), "second_renewal": (2, 2), "established": (3, 99)}   # quarters as a member
PROSPECT_SEGMENTS = {  # (former member?, engaged podcast listener?) -> name
    (0, 1): "warm_listener", (0, 0): "cold", (1, 1): "win_back", (1, 0): "lapsed_low_podcast"}
PODCAST_SEGMENTS = {1: "high_podcast", 0: "low_podcast"}
PERIODS = {"2017_spring_fall": (1, 2, 3), "2018_spring_fall": (5, 6, 7), "2019_spring_fall": (9, 10, 11)}


# Inputs:  the customer x quarter table from data_prep.build_analysis_table()
# Outputs: DataFrames of rates with counts (returned); pipeline.py saves them to outputs/results/


def standard_error(rate, n):
    """Sampling error of a share: sqrt(p (1 - p) / n). Treats rows as independent (people repeat across quarters,
    so true errors are somewhat larger; robustness/ reports customer-clustered errors)."""
    return np.sqrt(rate * (1 - rate) / n)


def _rate_table(rows: pd.DataFrame, by: list, outcome: str) -> pd.DataFrame:
    """Group, then count rows and average the 0/1 outcome; adds the standard error."""
    table = rows.groupby(by, observed=True)[outcome].agg(n="size", rate="mean").reset_index()
    table["se"] = standard_error(table.rate, table.n)
    return table


def discounting_regions(table: pd.DataFrame, quarters=None) -> pd.DataFrame:
    """Rows from the regions that ran discounts (all but Panem), optionally only some quarters."""
    rows = table[table.is_treated_region == 1]
    return rows if quarters is None else rows[rows.quarter_index.isin(quarters)]


def prospects(rows: pd.DataFrame) -> pd.DataFrame:
    """Non-members (never joined, or former members), labelled with their segment."""
    rows = rows[rows.is_prospect == 1].copy()
    rows["segment"] = [PROSPECT_SEGMENTS[key] for key in zip(rows.is_lapsed, rows.is_high_podcast)]
    return rows


def members(rows: pd.DataFrame) -> pd.DataFrame:
    """Members deciding whether to stay, labelled with podcast segment and tenure group."""
    rows = rows[rows.status == "member"].copy()
    rows["segment"] = rows.is_high_podcast.map(PODCAST_SEGMENTS)
    rows["tenure_group"] = pd.cut(rows.member_tenure, bins=[0, 1, 2, 99], labels=list(TENURE_GROUPS)).astype(str)
    return rows


def signup_by_price(table: pd.DataFrame) -> pd.DataFrame:
    """Sign-up rate at each price paid, within each base-price era ($15, then $12). Quarters 1-11, discounting regions."""
    rows = prospects(discounting_regions(table, range(1, 12)))
    return _rate_table(rows, ["base_price", "membership_price"], "sign_up_flag")


def stay_by_price(table: pd.DataFrame) -> pd.DataFrame:
    """Share of members who stay at each price, within each base-price era. Quarters 1-11, discounting regions."""
    rows = members(discounting_regions(table, range(1, 12)))
    return _rate_table(rows, ["base_price", "membership_price"], "stayed")


def signup_by_segment_and_discount(table: pd.DataFrame) -> pd.DataFrame:
    """$12 era: sign-up rate for each prospect segment at each discount ($0 = list price), plus segment shares.
    Adds, per segment: list_rate (joins anyway), uplift = rate - list_rate (joins because of the offer),
    incremental_share = uplift / rate (share of offer joiners the offer actually won)."""
    rows = prospects(discounting_regions(table, CURRENT_ERA_QUARTERS))
    cells = _rate_table(rows, ["segment", "discount_depth"], "sign_up_flag")
    cells["share_of_prospects"] = cells.segment.map(rows.segment.value_counts(normalize=True))
    cells["list_rate"] = cells.segment.map(cells[cells.discount_depth == 0].set_index("segment").rate)
    cells["uplift"] = cells.rate - cells.list_rate
    cells["incremental_share"] = np.where(cells.discount_depth > 0, cells.uplift / cells.rate, np.nan)
    cells["price"] = 12 - cells.discount_depth
    cells["revenue_per_prospect"] = cells.rate * cells.price       # first quarter only
    return cells


def stay_by_tenure_and_price(table: pd.DataFrame) -> pd.DataFrame:
    """$12 era: share of members who stay, by podcast segment, tenure group and price ($7-$11; every member had an offer)."""
    rows = members(discounting_regions(table, CURRENT_ERA_QUARTERS))
    return _rate_table(rows, ["segment", "tenure_group", "membership_price"], "stayed")


def never_member_share_high_podcast(table: pd.DataFrame) -> float:
    """$12 era: share of never-member prospects who are engaged podcast listeners (the projection's starting mix)."""
    rows = prospects(discounting_regions(table, CURRENT_ERA_QUARTERS))
    return float(rows[rows.is_lapsed == 0].is_high_podcast.mean())


def prospects_per_quarter(table: pd.DataFrame) -> float:
    """$12 era: average number of prospect rows per quarter in the discounting regions (for holdout sizing)."""
    rows = prospects(discounting_regions(table, CURRENT_ERA_QUARTERS))
    return len(rows) / len(CURRENT_ERA_QUARTERS)


def base_cut_two_by_two(table: pd.DataFrame) -> pd.DataFrame:
    """List-price sign-up rate (no offer), cut regions vs Panem, in the same three seasons of 2017, 2018 and 2019.
    The $15 -> $12 cut happened in 2019 spring in every region except Panem.
      change_vs_panem(2018 -> 2019) = what the cut might have done   (a difference-in-differences, in points)
      change_vs_panem(2017 -> 2018) = the same calculation with NO cut: should be ~0 if Panem is a fair comparison."""
    rows = prospects(table[table.discount_flag == 0])
    rows["group"] = np.where(rows.is_treated_region == 1, "cut_regions", "panem")
    rows["period"] = rows.quarter_index.map({q: name for name, quarters in PERIODS.items() for q in quarters})
    return _rate_table(rows.dropna(subset=["period"]), ["group", "period"], "sign_up_flag")


def base_cut_gap_by_quarter(table: pd.DataFrame) -> pd.DataFrame:
    """List-price sign-up rate per quarter, cut regions vs Panem, and the gap (cut - Panem) in points.
    Shows whether Panem is a steady comparison: before the cut the gap should hold still if it is."""
    rows = prospects(table[table.discount_flag == 0])
    rows["group"] = np.where(rows.is_treated_region == 1, "cut_regions", "panem")
    by_quarter = rows.groupby(["quarter_index", "group"]).sign_up_flag.mean().unstack()
    by_quarter["gap"] = by_quarter.cut_regions - by_quarter.panem
    by_quarter["after_cut"] = by_quarter.index >= CURRENT_ERA_QUARTERS[0]
    return by_quarter.reset_index()


def gap_change(two_by_two: pd.DataFrame, before: str, after: str) -> float:
    """(cut regions - Panem) in `after` minus the same gap in `before`, in sign-up rate points."""
    rate = two_by_two.set_index(["group", "period"]).rate
    gap = lambda period: rate["cut_regions", period] - rate["panem", period]
    return float(gap(after) - gap(before))
