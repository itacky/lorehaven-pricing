"""Who is incremental?  Prospect uplift by propensity segment, using the random offer + random depth.

Population: prospects (status never/lapsed) in treated regions, t >= 1.
Because offers and depth are randomized (see 01), within a segment the no-offer group is a valid
counterfactual for the offered groups.

Per segment, estimated with region x season fixed effects:
  y_i = a_(region,t) + sum_{k=1..5} tau_k * 1[off_i = k] + e_i
    y_i     1 if prospect i signs up this season
    off_i   dollars off list price (0 = no offer, list price)
    tau_k   UPLIFT of a $k discount: extra sign-up probability vs list price
  p0  = sign-up rate at list price (no offer)            [observed mean of the off = 0 group]
  pk  = p0 + tau_k = sign-up rate with $k off             [estimate]

Population decomposition at a $k offer (ASSUMPTION: monotonicity - no one is LESS likely to join
because of a discount; checked by requiring every tau_k >= 0):
  Would join anyway  = p0               (sign up even at list price; a discount only costs money)
  Persuaded by $k    = tau_k            (join only because of the discount: the incremental ones)
  Not reached by $k  = 1 - p0 - tau_k   (don't join even with $k off)
These are SHARES OF THE SEGMENT, not labels on individuals: we never see the same person both ways.

Efficiency of a $k offer, first season only:
  incremental share of discounted sign-ups = tau_k / pk
  discount $ per incremental sign-up       = k * pk / tau_k
    (k dollars go to EVERY sign-up who got the offer, pk of them, to buy tau_k extra sign-ups)

Usage: python analysis/03_incrementality_segments.py <prepared_parquet> <out_dir>
"""
import sys
import numpy as np
import pandas as pd

PODCAST, SOCIAL = "customer_podcast_score", "customer_social_score"


def uplift(df):
    """OLS of y on depth dummies with region x season FE (within-transformation)."""
    D = pd.get_dummies(df.off.astype(int), prefix="off", dtype=float).drop(columns="off_0")
    cols = list(D.columns)
    X = pd.concat([D, df[["y", "region_t"]]], axis=1)
    dm = X[cols + ["y"]] - X.groupby("region_t")[cols + ["y"]].transform("mean")
    Xm, ym = dm[cols].to_numpy(), dm.y.to_numpy()
    XtX_inv = np.linalg.inv(Xm.T @ Xm)
    b = XtX_inv @ Xm.T @ ym
    e = ym - Xm @ b
    se = np.sqrt(np.diag(XtX_inv @ ((Xm * e[:, None]).T @ (Xm * e[:, None])) @ XtX_inv))
    return dict(zip(range(1, 6), b)), dict(zip(range(1, 6), se))


def segment_table(df, seg_col):
    rows = []
    for seg, g in df.groupby(seg_col, observed=True):
        tau, se = uplift(g)
        p0 = g.loc[g.off == 0, "y"].mean()
        row = dict(segment=seg, n=len(g), share_of_prospects=len(g) / len(df), p0_list=p0)
        for k in range(1, 6):
            row[f"uplift_{k}"] = tau[k]
            row[f"uplift_{k}_se"] = se[k]
        pk = p0 + tau[5]
        row.update(would_join_anyway=p0, persuaded_by_5=tau[5], not_reached_by_5=1 - pk,
                   incremental_share_at_5=tau[5] / pk, dollars_per_incr_signup_at_1=1 * (p0 + tau[1]) / tau[1],
                   dollars_per_incr_signup_at_5=5 * pk / tau[5], monotone=all(tau[k] >= 0 for k in tau))
        rows.append(row)
    return pd.DataFrame(rows)


def main(path, out_dir):
    d = pd.read_parquet(path)
    d = d[(d.treated == 1) & (d.t >= 1) & d.status.isin(["never", "lapsed"])].copy()
    d["y"] = d.sign_up_flag
    d["region_t"] = d.region_name + "_" + d.t.astype(str)
    d["era"] = np.where(d.base == 15, "base15", "base12")
    pb = pd.cut(d[PODCAST], [-0.01, 0.40, 0.55, 1.0], labels=["P<0.40", "P0.40-0.55", "P>=0.55"])
    sb = pd.cut(d[SOCIAL], [-0.01, 0.425, 1.0], labels=["S<0.425", "S>=0.425"])
    d["cell"] = pb.astype(str) + " | " + sb.astype(str)
    d["podcast_band"] = pb.astype(str)
    d["status_x_podcast"] = d.status + " | " + np.where(d[PODCAST] >= 0.5, "P>=0.5", "P<0.5")

    L = []
    show = ["segment", "n", "share_of_prospects", "p0_list", "uplift_1", "uplift_3", "uplift_5",
            "would_join_anyway", "persuaded_by_5", "not_reached_by_5", "incremental_share_at_5",
            "dollars_per_incr_signup_at_1", "dollars_per_incr_signup_at_5", "monotone"]
    for name, col in [("ALL", None), ("podcast band", "podcast_band"), ("podcast x social cell", "cell"),
                      ("status x podcast", "status_x_podcast")]:
        if col is None:
            d["_all"] = "all prospects"; col = "_all"
        t = segment_table(d, col)
        t.to_csv(f"{out_dir}/03_{name.replace(' ', '_')}.csv", index=False)
        L.append(f"\n== by {name} ==\n" + t[show].round(4).to_string(index=False))
        # era split for robustness
        te = pd.concat([segment_table(g, col).assign(era=e) for e, g in d.groupby("era")])
        te.to_csv(f"{out_dir}/03_{name.replace(' ', '_')}_by_era.csv", index=False)
        L.append(f"-- same, by base-price era --\n" + te[["era"] + show].round(4).to_string(index=False))
    txt = "\n".join(L)
    open(f"{out_dir}/03_incrementality_segments.txt", "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
