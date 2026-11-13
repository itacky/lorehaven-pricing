"""Checks that the pricing strategy depends on.

A) DiD on the 2019 base cut ($15 -> $12, treated regions vs Panem), prospects at LIST price only.
   In treated regions the no-offer prospects are a random 75% (see 01), so they are comparable to
   Panem prospects (never offered). Grouped logit on region x season cells:
     logit P(sign-up) = a_region + g_season + delta * Treat x Post
       a_region  region intercept;  g_season  season intercept (shared shocks)
       Treat = 1 for the 5 discounting regions; Post = 1 from 2019 spring (t >= 9)
       delta     DiD effect of the base cut on log-odds; exp(delta) = odds ratio
   Benchmark: the randomized-depth logit (04) predicts a $3 cut moves log-odds by -3 * beta.
   Placebo: same model on pre-period only with a fake Post from t >= 5.

B) Reference-price effect for members: does last season's price matter, given today's price?
   Members are re-drawn a random depth each season, so last season's price is random too.
     stay = a_(region,t) + b1 * price_now + b2 * price_last + e      (linear probability)
   b2 > 0 would mean a member who paid MORE last season is more likely to stay at today's price
   (i.e. price increases vs last season hurt beyond the price level). Excludes t = 9 (base changed).

C) First-season revenue per prospect by segment and depth, from the 03 uplift estimates:
     R(k) = (p0 + uplift_k) * (base - k)     [$ per prospect per season, k = dollars off]

Usage: python analysis/05_strategy_checks.py <prepared_parquet> <out_dir>
"""
import sys
import numpy as np
import pandas as pd
import statsmodels.api as sm

BETA_ACQ = -0.3656  # from 04 (randomized-depth logit, sign-up)


def did(df, post_from):
    c = df.groupby(["region_name", "t"]).y.agg(succ="sum", n="size").reset_index()
    c["treat"] = (c.region_name != "panem").astype(int)
    c["tp"] = c.treat * (c.t >= post_from)
    X = pd.concat([pd.get_dummies(c.region_name, dtype=float),
                   pd.get_dummies(c.t, prefix="t", drop_first=True, dtype=float), c[["tp"]]], axis=1)
    m = sm.GLM(np.column_stack([c.succ, c.n - c.succ]), X, family=sm.families.Binomial()).fit(cov_type="HC1")
    return m.params["tp"], m.bse["tp"]


def main(path, out_dir):
    d = pd.read_parquet(path)
    d = d[d.t >= 1].copy()
    d["y"] = d.sign_up_flag
    L = []

    # A) DiD
    A = d[d.status.isin(["never", "lapsed"]) & (d.discount_flag == 0)]
    dl, se = did(A, 9)
    pl, pse = did(A[A.t <= 8], 5)
    pred = -3 * BETA_ACQ
    L.append("A) DiD, base cut $15->$12, prospects at list price (log-odds scale; robust SE; "
             "NOTE: only 1 control region, so SEs are optimistic)")
    L.append(f"   DiD delta = {dl:.3f} (se {se:.3f}); odds ratio = {np.exp(dl):.2f}")
    L.append(f"   Placebo (pre-period only, fake cut at t>=5): {pl:.3f} (se {pse:.3f})")
    L.append(f"   Randomized-depth prediction for a $3 cut: {pred:.3f}; odds ratio = {np.exp(pred):.2f}")
    r = A.assign(grp=np.where(A.treated == 1, "treated", "panem"), post=A.t >= 9).groupby(["grp", "post"]).y.mean()
    L.append("   raw list-price sign-up rates (pre / post):\n" + r.unstack().round(4).to_string())

    # B) reference price
    B = d[(d.treated == 1) & (d.status == "member") & (d.l_discount == 1) & (d.t != 9)].copy()
    B["price_last"] = B.base - B.l_off
    B["region_t"] = B.region_name + "_" + B.t.astype(str)
    cols = ["y", "membership_price", "price_last"]
    dm = B[cols] - B.groupby("region_t")[cols].transform("mean")
    X = dm[["membership_price", "price_last"]].to_numpy(float); yv = dm.y.to_numpy(float)
    XtXi = np.linalg.inv(X.T @ X); b = XtXi @ X.T @ yv; e = yv - X @ b
    se = np.sqrt(np.diag(XtXi @ ((X * e[:, None]).T @ (X * e[:, None])) @ XtXi))
    L.append(f"\nB) Reference price, members (n={len(B):,}), linear prob. with region x season FE:")
    L.append(f"   price_now:  {100*b[0]:.3f} pp per $ (se {100*se[0]:.3f})")
    L.append(f"   price_last: {100*b[1]:.3f} pp per $ (se {100*se[1]:.3f})")
    B["change"] = np.sign(B.membership_price - B.price_last).map({-1: "price fell", 0: "same", 1: "price rose"})
    t = B.groupby(["membership_price", "change"]).y.mean().unstack()
    L.append("   stay rate by current price x direction of change vs last season:\n" + t.round(4).to_string())

    # C) first-season revenue per prospect by segment x depth
    seg = pd.read_csv(f"{out_dir}/03_status_x_podcast_by_era.csv")
    rows = []
    for _, s in seg.iterrows():
        base = 15 if s.era == "base15" else 12
        row = {"era": s.era, "segment": s.segment, "list": s.p0_list * base}
        for k in range(1, 6):
            row[f"${k}_off"] = (s.p0_list + s[f"uplift_{k}"]) * (base - k)
        rows.append(row)
    C = pd.DataFrame(rows)
    C.to_csv(f"{out_dir}/05_first_season_revenue_per_prospect.csv", index=False)
    L.append("\nC) First-season revenue per prospect ($), by segment and offer depth:\n" + C.round(3).to_string(index=False))
    txt = "\n".join(L)
    open(f"{out_dir}/05_strategy_checks.txt", "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
