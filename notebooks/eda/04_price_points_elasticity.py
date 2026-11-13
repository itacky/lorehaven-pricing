"""Sign-up and retention rates by price point, arc elasticities, and the logit price-response model.

Populations (treated regions, t >= 1; prices vary only through the randomized offer/depth):
  ACQ  prospects: y = sign_up_flag.     Prices: $10-15 (base $15 era), $7-12 (base $12 era).
  RET  members last season: y = stayed. Prices: $10-14 (base $15 era), $7-11 (base $12 era).
       (Panem members at $15 are shown for reference only: different region, not randomized.)

1) Rates by price point, within era: n, rate, 95% CI = rate +/- 1.96*sqrt(rate*(1-rate)/n).

2) Arc (midpoint) elasticity between adjacent price points P1 < P2 with rates Q1, Q2:
     E_arc = [(Q2 - Q1) / ((Q1 + Q2)/2)]  /  [(P2 - P1) / ((P1 + P2)/2)]
   = % change in the rate per 1% change in price, both measured against the midpoint.

3) Logit model, fit on cell counts (region x season x price) with a region x season intercept:
     P(y=1) = 1 / (1 + exp(-(a_(region,t) + beta * price)))
       a_(region,t) baseline log-odds for each region x season (absorbs base price, marketing, season)
       beta         change in log-odds of signing up / staying per +$1
   Point elasticity at price p:   E(p) = beta * p * (1 - P(p))
     (derivative dP/dp = beta * P * (1-P); multiply by p/P to convert to % terms)

4) What elasticity means for value (derived, see write-up):
   ACQ, first-season revenue per prospect R = p * s(p)  ->  dlnR/dlnp = 1 + E_s
   RET, expected future revenue per member V = p * r / (1 - r)   (constant price p, stay prob r)
        dlnV/dlnp = 1 + E_r / (1 - r)
   A price cut raises the metric when the right-hand side is negative.

Usage: python analysis/04_price_points_elasticity.py <prepared_parquet> <out_dir>
"""
import sys
import numpy as np
import pandas as pd
import statsmodels.api as sm


def rates(df):
    g = df.groupby(["era", "price"]).y.agg(n="size", rate="mean").reset_index()
    g["ci95"] = 1.96 * np.sqrt(g.rate * (1 - g.rate) / g.n)
    out = []
    for era, e in g.groupby("era"):
        e = e.sort_values("price").reset_index(drop=True)
        q1, q2, p1, p2 = e.rate.shift(), e.rate, e.price.shift(), e.price
        e["arc_elasticity_vs_prev"] = ((q2 - q1) / ((q1 + q2) / 2)) / ((p2 - p1) / ((p1 + p2) / 2))
        out.append(e)
    return pd.concat(out)


def logit(df, extra=None):
    """Grouped binomial logit with region x season dummies. extra: optional 0/1 column interacted with price."""
    keys = ["region_t", "price"] + ([extra] if extra else [])
    c = df.groupby(keys).y.agg(succ="sum", n="size").reset_index()
    X = pd.get_dummies(c.region_t, dtype=float)                      # one intercept per region x season
    X["price"] = c.price
    if extra:
        X[extra] = c[extra]; X["price_x_" + extra] = c.price * c[extra]
    m = sm.GLM(np.column_stack([c.succ, c.n - c.succ]), X, family=sm.families.Binomial()).fit()
    c["pred"] = m.predict(X)
    return m, c


def point_elasticity(cells, beta_col):
    """n-weighted average of beta * p * (1 - P) at each price point, by era."""
    e = cells.assign(E=cells[beta_col] * cells.price * (1 - cells.pred))
    return e.groupby(["era", "price"]).apply(lambda g: pd.Series({
        "obs_rate": g.succ.sum() / g.n.sum(), "logit_pred": np.average(g.pred, weights=g.n),
        "point_elasticity": np.average(g.E, weights=g.n)}), include_groups=False).reset_index()


def main(path, out_dir):
    d = pd.read_parquet(path)
    d = d[d.t >= 1].copy()
    d["y"] = d.sign_up_flag
    d["price"] = d.membership_price.astype(int)
    d["era"] = np.where(d.base == 15, "base15", "base12")
    d["region_t"] = d.region_name + "_" + d.t.astype(str)
    d["hi_podcast"] = (d.customer_podcast_score >= 0.5).astype(int)
    T = d[d.treated == 1]
    sets = {"ACQ": T[T.status.isin(["never", "lapsed"])], "RET": T[T.status == "member"]}
    L = []
    for name, df in sets.items():
        r = rates(df)
        r.to_csv(f"{out_dir}/04_{name}_rates_by_price.csv", index=False)
        L.append(f"\n===== {name}: observed rates by price point =====\n" + r.round(4).to_string(index=False))
        m, cells = logit(df)
        b, se = m.params["price"], m.bse["price"]
        cells["era"] = np.where(cells.region_t.str.split("_").str[-1].astype(int) >= 9, "base12", "base15")
        cells.loc[cells.region_t.str.startswith("panem"), "era"] = "base15"
        cells["beta"] = b
        pe = point_elasticity(cells, "beta")
        pe.to_csv(f"{out_dir}/04_{name}_logit_elasticity.csv", index=False)
        L.append(f"\n{name} logit: beta = {b:.4f} per $ (se {se:.4f}); odds multiply by exp(beta) = {np.exp(b):.4f} per +$1")
        L.append(pe.round(4).to_string(index=False))
        # segment logit (podcast >= 0.5), for the simulator
        m2, c2 = logit(df, "hi_podcast")
        b_lo, b_hi = m2.params["price"], m2.params["price"] + m2.params["price_x_hi_podcast"]
        L.append(f"{name} segment logit: beta(podcast<0.5) = {b_lo:.4f}, beta(podcast>=0.5) = {b_hi:.4f}, "
                 f"interaction se = {m2.bse['price_x_hi_podcast']:.4f}")
        pd.DataFrame({"term": m2.params.index, "coef": m2.params.values, "se": m2.bse.values}) \
          .query("term in ['price','hi_podcast','price_x_hi_podcast']").to_csv(f"{out_dir}/04_{name}_segment_logit.csv", index=False)
    P = d[(d.treated == 0) & (d.status == "member")]
    L.append(f"\nREFERENCE (not randomized): Panem members at $15, stay rate = {P.y.mean():.4f} (n={len(P):,}); "
             f"by year: {P.groupby('year').y.mean().round(4).to_dict()}")
    txt = "\n".join(L)
    open(f"{out_dir}/04_price_points_elasticity.txt", "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
