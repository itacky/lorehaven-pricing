"""Which customer types respond most to price?  Uses only randomized price variation.

Two outcomes (treated regions, t >= 1):
  ACQ  prospects (status never/lapsed): y = sign_up_flag, price = membership_price
       (price varies through the random offer AND random depth: $10-15 pre-cut, $7-12 post-cut)
  RET  members last season: y = sign_up_flag (stayed), price = membership_price
       (members are always discounted, so price varies through random depth only)

Model inside any subgroup (linear probability model with fixed effects):
  y_i = a_(region, t) + b * price_i + e_i
    y_i         1 if the customer signs up (ACQ) / stays (RET) this season, else 0
    a_(region,t) a separate intercept for every region x season (absorbs base price, marketing, seasonality)
    price_i     price offered/paid this season, in $
    b           change in probability per +$1 of price (negative = price-sensitive)
  Estimated by demeaning y and price within region x season, then slope = sum(y~ * p~) / sum(p~^2).
  Robust (HC0) standard error: sqrt(sum(p~^2 * e^2)) / sum(p~^2).

Elasticity at the subgroup mean:  E = b * mean(price) / mean(y)
  = % change in sign-up (or stay) probability for a 1% change in price.

Joint interaction model (all scores at once, scores on their 0-1 scale):
  y = a_(region,t) + b0*price + sum_k g_k*score_k + sum_k d_k*(price x score_k) + e
    d_k = how much the price slope changes moving score_k from 0 to 1, holding the other scores fixed.

Display score: zeros are treated as missing (see data notes), so display rows with 0 are excluded
from display-specific results and the joint model uses display_missing as its own control.

Usage: python analysis/02_price_response_by_propensity.py <prepared_parquet> <out_dir>
"""
import sys
import numpy as np
import pandas as pd

SCORES = {"tv": "customer_tv_score", "radio": "customer_radio_score", "social": "customer_social_score",
          "podcast": "customer_podcast_score", "display": "customer_display_score"}


def demean(df, cols, fe):
    return df[cols] - df.groupby(fe)[cols].transform("mean")


def slope(df, fe):
    d = demean(df, ["y", "price"], fe)
    p, y = d.price.to_numpy(), d.y.to_numpy()
    sxx = (p * p).sum()
    b = (p * y).sum() / sxx
    e = y - b * p
    se = np.sqrt((p * p * e * e).sum()) / sxx
    return b, se


def by_decile(df, fe, col, nbins=10):
    sub = df[df[col] > 0] if col == SCORES["display"] else df
    bins = pd.qcut(sub[col].rank(method="first"), nbins, labels=False)
    rows = []
    for k, g in sub.groupby(bins):
        b, se = slope(g, fe)
        rows.append(dict(decile=k + 1, score_lo=g[col].min(), score_hi=g[col].max(), n=len(g),
                         mean_y=g.y.mean(), mean_price=g.price.mean(), slope_pp_per_dollar=100 * b,
                         se_pp=100 * se, elasticity=b * g.price.mean() / g.y.mean()))
    return pd.DataFrame(rows)


def joint(df, fe):
    df = df.copy()
    df.loc[df.display_missing == 1, SCORES["display"]] = 0.0  # missing -> 0 plus its own dummy below
    xs = ["price"] + list(SCORES.values()) + ["display_missing"]
    for s in SCORES.values():
        df["px_" + s] = df.price * df[s]
        xs.append("px_" + s)
    df["px_display_missing"] = df.price * df.display_missing
    xs.append("px_display_missing")
    d = demean(df, ["y"] + xs, fe)
    X, y = d[xs].to_numpy(), d.y.to_numpy()
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    e = y - X @ beta
    meat = (X * e[:, None]).T @ (X * e[:, None])
    se = np.sqrt(np.diag(XtX_inv @ meat @ XtX_inv))
    return pd.DataFrame({"term": xs, "coef_pp": 100 * beta, "se_pp": 100 * se, "t": beta / se})


def threshold_search(df, fe, col, grid):
    """For each cutoff c: y = a_(region,t) + b*price + g*H + d*(price x H), H = 1[score >= c].
    Report the cutoff that minimizes residual sum of squares (best single split)."""
    out = []
    base = demean(df, ["y", "price"], fe)
    for c in grid:
        H = (df[col] >= c).astype(float)
        tmp = pd.DataFrame({"H": H, "pH": df.price * H, "region_t": df[fe]})
        dm = tmp[["H", "pH"]] - tmp.groupby("region_t")[["H", "pH"]].transform("mean")
        X = np.column_stack([base.price, dm.H, dm.pH])
        beta, rss, *_ = np.linalg.lstsq(X, base.y.to_numpy(), rcond=None)
        hi, lo = df[H == 1], df[H == 0]
        out.append(dict(cutoff=c, share_high=H.mean(), rss=float(rss[0]),
                        slope_low_pp=100 * beta[0], slope_high_pp=100 * (beta[0] + beta[2])))
    r = pd.DataFrame(out)
    r["delta_rss_vs_best"] = r.rss - r.rss.min()
    return r


def main(path, out_dir):
    d = pd.read_parquet(path)
    d = d[(d.treated == 1) & (d.t >= 1)].copy()
    d["y"] = d.sign_up_flag
    d["price"] = d.membership_price.astype(float)
    d["region_t"] = d.region_name + "_" + d.t.astype(str)
    sets = {"ACQ": d[d.status.isin(["never", "lapsed"])], "RET": d[d.status == "member"]}
    lines = []
    lines.append("score correlations (prospects):\n" + sets["ACQ"][list(SCORES.values())].corr().round(3).to_string())
    for name, df in sets.items():
        b, se = slope(df, "region_t")
        lines.append(f"\n===== {name}: n={len(df):,}  overall slope = {100*b:.3f} pp per $ (se {100*se:.3f}), "
                     f"mean y = {df.y.mean():.4f}, elasticity = {b*df.price.mean()/df.y.mean():.3f}")
        for short, col in SCORES.items():
            t = by_decile(df, "region_t", col)
            t.to_csv(f"{out_dir}/02_{name}_{short}_deciles.csv", index=False)
            lines.append(f"\n-- {name} by {short} decile --\n" + t.round(4).to_string(index=False))
        j = joint(df, "region_t")
        j.to_csv(f"{out_dir}/02_{name}_joint.csv", index=False)
        lines.append(f"\n-- {name} joint interaction model --\n" + j.round(4).to_string(index=False))
    txt = "\n".join(lines)
    open(f"{out_dir}/02_price_response_by_propensity.txt", "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
