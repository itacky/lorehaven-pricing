"""Load the raw Lorehaven CSVs and derive the columns every model uses.

Data folder: environment variable LOREHAVEN_DATA_DIR, default data/raw/ (repo-relative).

Season index: quarter_index 0..11 = 2017 winter .. 2019 fall.
ASSUMPTION: seasons run winter -> spring -> summer -> fall within a year (no date field in the data).
ASSUMPTION: 2017 winter (quarter 0) is the launch quarter, so nobody was a member before it.
  Support: in every region, member_count at quarter 0 equals that quarter's sign-ups.
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
SEASON_ORDER = {"winter": 0, "spring": 1, "summer": 2, "fall": 3}
CONTROL_REGION = "panem"            # never discounted, base price stays $15
ORIGINAL_BASE_PRICE = 15
CUT_BASE_PRICE = 12
BASE_CUT_QUARTER_INDEX = 9          # 2019 spring: first quarter at $12 outside Panem (observed)
PODCAST_SEGMENT_CUTOFF = 0.5        # podcast propensity >= 0.5 -> "high podcast" segment

PANEL_DTYPES = {
    "region_id": "int8", "region_name": "category", "year": "int16", "season": "category",
    "customer_id": "int32", "search_flag": "int8", "social_ad_impressions": "int16",
    "podcast_ad_listen": "int16", "membership_price": "int8", "discount_flag": "int8", "sign_up_flag": "int8",
}
PROPENSITY_DTYPES = {
    "customer_id": "int32", "year": "int16", "customer_tv_score": "float32", "customer_radio_score": "float32",
    "customer_social_score": "float32", "customer_podcast_score": "float32", "customer_display_score": "float32",
}
SCORE_COLUMNS = [c for c in PROPENSITY_DTYPES if c.endswith("_score")]


def data_dir() -> Path:
    path = Path(os.environ.get("LOREHAVEN_DATA_DIR", REPO_ROOT / "data" / "raw"))
    if not path.exists():
        raise FileNotFoundError(f"Data folder not found: {path}. Put the CSVs in data/raw/ "
                                f"or set LOREHAVEN_DATA_DIR.")
    return path


def quarter_index(year: pd.Series, season: pd.Series) -> pd.Series:
    return ((year.astype(int) - 2017) * 4 + season.astype(str).map(SEASON_ORDER)).astype("int8")


def load_aggregate() -> pd.DataFrame:
    """Region x quarter marketing table. Known gaps are set to NaN (they are recorded as 0 with spend > 0)."""
    agg = pd.read_csv(data_dir() / "aggregate.csv")
    agg["quarter_index"] = quarter_index(agg.year, agg.season)
    westeros_winter = (agg.region_name == "westeros") & (agg.season == "winter")
    agg.loc[westeros_winter, "tv_ratings"] = np.nan
    display_gap = (agg.display_impressions == 0) & (agg.display_spend > 0)
    agg.loc[display_gap, "display_impressions"] = np.nan
    return agg


def load_panel(columns=None) -> pd.DataFrame:
    usecols = columns or list(PANEL_DTYPES)
    dtypes = {c: PANEL_DTYPES[c] for c in usecols}
    return pd.read_csv(data_dir() / "customer_panel.csv", usecols=usecols, dtype=dtypes)


def load_propensities() -> pd.DataFrame:
    props = pd.read_csv(data_dir() / "customer_propensities.csv", usecols=list(PROPENSITY_DTYPES),
                        dtype=PROPENSITY_DTYPES)
    props["display_score_missing"] = (props.customer_display_score == 0).astype("int8")
    props.loc[props.display_score_missing == 1, "customer_display_score"] = np.nan   # zeros = missing
    return props


def add_derived_columns(panel: pd.DataFrame) -> pd.DataFrame:
    """Status from the prior quarter, sign-up / churn events, base price and discount depth."""
    panel = panel.copy()
    panel["quarter_index"] = quarter_index(panel.year, panel.season)
    panel = panel.sort_values(["customer_id", "quarter_index"], ignore_index=True)
    panel["is_treated_region"] = (panel.region_name.astype(str) != CONTROL_REGION).astype("int8")
    panel["base_price"] = np.where((panel.is_treated_region == 1) & (panel.quarter_index >= BASE_CUT_QUARTER_INDEX),
                                   CUT_BASE_PRICE, ORIGINAL_BASE_PRICE).astype("int8")
    panel["discount_depth"] = (panel.base_price - panel.membership_price).astype("int8")

    by_customer = panel.groupby("customer_id", sort=False)
    panel["was_member_last_quarter"] = by_customer.sign_up_flag.shift().fillna(0).astype("int8")  # launch assumption
    was_ever_member_before = by_customer.sign_up_flag.cummax().groupby(panel.customer_id).shift().fillna(0)
    panel["status"] = np.select(
        [panel.was_member_last_quarter == 1, was_ever_member_before == 1],
        ["member", "lapsed_prospect"], "never_prospect")
    panel["is_prospect"] = panel.status.isin(["never_prospect", "lapsed_prospect"]).astype("int8")
    panel["new_signup"] = ((panel.was_member_last_quarter == 0) & (panel.sign_up_flag == 1)).astype("int8")
    panel["is_lapsed"] = (panel.status == "lapsed_prospect").astype("int8")
    panel["churned"] = ((panel.was_member_last_quarter == 1) & (panel.sign_up_flag == 0)).astype("int8")
    panel["stayed"] = 1 - panel.churned
    panel["last_quarter_discount_depth"] = by_customer.discount_depth.shift()
    panel["region_quarter"] = panel.region_name.astype(str) + "_q" + panel.quarter_index.astype(str)
    return panel


def build_analysis_table(cache=True) -> pd.DataFrame:
    """Panel + derived columns + same-year propensity scores. Cached as parquet (gitignored)."""
    cache_path = REPO_ROOT / "data" / "interim" / "analysis_table.parquet"
    if cache and cache_path.exists():
        return pd.read_parquet(cache_path)
    table = add_derived_columns(load_panel())
    table = table.merge(load_propensities(), on=["customer_id", "year"], how="left", validate="many_to_one")
    if table.customer_podcast_score.isna().any():
        raise ValueError("Propensity join left customers without scores")
    table["is_high_podcast"] = (table.customer_podcast_score >= PODCAST_SEGMENT_CUTOFF).astype("int8")
    if cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(cache_path, index=False)
    return table
