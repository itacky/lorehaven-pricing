"""Build one analysis-ready customer x season table from the raw CSVs.

Usage: python analysis/prep.py <raw_dir> <out_parquet>
  raw_dir must contain customer_panel.csv and customer_propensities.csv.

Derived columns (all computed, none imputed):
  t            season index 0..11 (2017 winter = 0). ASSUMPTION: seasons run winter->spring->summer->fall.
  treated      1 for non-Panem regions (discounts + 2019 base cut), 0 for Panem.
  base         list price the customer faced that season: 12 if treated and t >= 9 (2019 spring), else 15.
  off          dollars off list = base - membership_price (0 when not discounted).
  l_member     1 if the customer was a member (sign_up_flag = 1) in the previous season.
  status       'member' (member last season), 'lapsed' (was a member before, not last season), 'never'.
  tenure       consecutive prior seasons as a member (0 for prospects).
  l_*          previous-season values of exposure / discount fields.
  display_missing  1 if customer_display_score == 0 (treated as missing, see data notes).
"""
import sys
import numpy as np
import pandas as pd

SEASON_ORDER = {"winter": 0, "spring": 1, "summer": 2, "fall": 3}
BASE_CUT_T = 9  # 2019 spring, first season at $12 outside Panem (observed in data)


def build(raw_dir: str) -> pd.DataFrame:
    p = pd.read_csv(f"{raw_dir}/customer_panel.csv")
    q = pd.read_csv(f"{raw_dir}/customer_propensities.csv")

    p["t"] = (p.year - 2017) * 4 + p.season.map(SEASON_ORDER)
    p = p.sort_values(["customer_id", "t"]).reset_index(drop=True)
    p["treated"] = (p.region_name != "panem").astype(int)
    p["base"] = np.where((p.treated == 1) & (p.t >= BASE_CUT_T), 12, 15)
    p["off"] = p.base - p.membership_price

    g = p.groupby("customer_id", sort=False)
    p["l_member"] = g.sign_up_flag.shift()
    p["l_discount"] = g.discount_flag.shift()
    p["l_off"] = g.off.shift()
    for c in ["search_flag", "social_ad_impressions", "podcast_ad_listen"]:
        p["l_" + c] = g[c].shift()
    ever_before = g.sign_up_flag.cummax().groupby(p.customer_id).shift()
    p["status"] = np.select([p.l_member == 1, ever_before == 1], ["member", "lapsed"], "never")
    p.loc[p.t == 0, "status"] = "first_period"

    # tenure: length of the current membership run, measured before this season
    run_id = (p.sign_up_flag != g.sign_up_flag.shift()).cumsum()
    run_len = p.groupby(run_id).cumcount() + 1
    p["tenure"] = np.where(p.l_member == 1, run_len.groupby(p.customer_id).shift(), 0)
    p["tenure"] = p.tenure.fillna(0)

    q = q.drop(columns=["season", "region_id", "region_name"])
    p = p.merge(q, on=["customer_id", "year"], how="left", validate="many_to_one")
    p["display_missing"] = (p.customer_display_score == 0).astype(int)
    return p


if __name__ == "__main__":
    raw_dir, out = sys.argv[1], sys.argv[2]
    df = build(raw_dir)
    assert df.customer_display_score.notna().all(), "propensity join left gaps"
    df.to_parquet(out, index=False)
    print(f"wrote {out}: {len(df):,} rows")
