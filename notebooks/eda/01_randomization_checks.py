"""Is discount assignment random?  Two separate assignment steps are tested:

  A. ELIGIBILITY: does a prospect (non-member last season) receive a discount offer at all?
     Population: treated regions, t >= 1, status in {never, lapsed}.  Outcome: discount_flag.
     (Members are excluded: in treated regions they are offered a discount 100% of the time,
      so there is no variation to test.)
  B. DEPTH: given an offer, how many dollars off ($1-$5)?
     Population: treated regions, t >= 1, discount_flag = 1 (prospects and members).  Outcome: off.

Checks for each:
  1. Standardized mean difference (SMD) of every covariate between groups.
       SMD = (mean_1 - mean_0) / sqrt((var_1 + var_0) / 2)
       mean_g, var_g = covariate mean and variance in group g.  |SMD| < 0.1 is the usual "balanced" bar.
  2. Assignment rate across deciles / levels of each covariate (should be flat).
  3. Joint test: linear regression of the assignment on ALL covariates plus sub-region and season
     dummies, F-test that all covariate coefficients are zero, R^2, and (A only) AUC.
     With millions of rows, tiny p-values can appear for trivial differences, so R^2 / AUC /
     SMD size are the substantive measures; p-values are reported for completeness.

Covariates are PRE-assignment where possible (propensity scores, last-season exposure, history).
Current-season exposure is reported separately because an offer could itself change it.

Usage: python analysis/01_randomization_checks.py <prepared_parquet> <out_dir>
"""
import sys
import numpy as np
import pandas as pd
from scipy import stats

SCORES = ["customer_tv_score", "customer_radio_score", "customer_social_score",
          "customer_podcast_score", "customer_display_score", "display_missing"]
LAG_EXPOSURE = ["l_search_flag", "l_social_ad_impressions", "l_podcast_ad_listen"]
CUR_EXPOSURE = ["search_flag", "social_ad_impressions", "podcast_ad_listen"]
HISTORY = ["lapsed", "l_discount", "tenure"]


def smd(x1, x0):
    return (x1.mean() - x0.mean()) / np.sqrt((x1.var() + x0.var()) / 2)


def auc(y, score):
    """Probability a random positive outranks a random negative (Mann-Whitney form)."""
    r = pd.Series(score).rank().to_numpy()
    n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def joint_test(df, y, covs):
    """OLS of y on covariates + sub-region + season dummies. F-test: covariates jointly zero."""
    fe = pd.get_dummies(df[["region_id", "t"]].astype(str), drop_first=True, dtype=np.float64)
    Xr = np.column_stack([np.ones(len(df)), fe.to_numpy()])           # restricted: FE only
    Xu = np.column_stack([Xr, df[covs].to_numpy(np.float64)])          # unrestricted: FE + covariates
    yv = df[y].to_numpy(np.float64)
    out = {}
    for name, X in [("r", Xr), ("u", Xu)]:
        beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
        fit = X @ beta
        out[name] = (((yv - fit) ** 2).sum(), fit)
    rss_r, rss_u = out["r"][0], out["u"][0]
    q, n, k = len(covs), len(yv), Xu.shape[1]
    F = ((rss_r - rss_u) / q) / (rss_u / (n - k))
    tss = ((yv - yv.mean()) ** 2).sum()
    # F-test for the FE themselves (are rates different by sub-region / season?)
    rss_c = tss
    q_fe = Xr.shape[1] - 1
    F_fe = ((rss_c - rss_r) / q_fe) / (rss_r / (n - Xr.shape[1]))
    return dict(n=n, F_cov=F, p_cov=stats.f.sf(F, q, n - k), R2_full=1 - rss_u / tss,
                R2_cov_increment=(rss_r - rss_u) / tss,
                F_fe=F_fe, p_fe=stats.f.sf(F_fe, q_fe, n - Xr.shape[1]), fitted=out["u"][1])


def decile_spread(df, y, col):
    """Max minus min assignment rate across deciles of col (or across its levels if few)."""
    x = df[col]
    bins = x if x.nunique() <= 12 else pd.qcut(x, 10, duplicates="drop")
    r = df.groupby(bins, observed=True)[y].mean()
    return r.max() - r.min()


def main(path, out_dir):
    d = pd.read_parquet(path)
    d = d[(d.treated == 1) & (d.t >= 1)].copy()
    d["lapsed"] = (d.status == "lapsed").astype(int)
    covs = SCORES + LAG_EXPOSURE + HISTORY
    lines = []

    # ---------------- A. ELIGIBILITY ----------------
    A = d[d.status.isin(["never", "lapsed"])].copy()
    A = A.dropna(subset=covs)
    lines.append(f"A. ELIGIBILITY among prospects (n={len(A):,}); overall offer rate = {A.discount_flag.mean():.4f}")
    t1 = []
    for c in covs + CUR_EXPOSURE:
        if c == "tenure":
            continue  # tenure is 0 for all prospects
        x1, x0 = A.loc[A.discount_flag == 1, c], A.loc[A.discount_flag == 0, c]
        t1.append((c, x1.mean(), x0.mean(), smd(x1, x0), decile_spread(A, "discount_flag", c)))
    tA = pd.DataFrame(t1, columns=["covariate", "mean_offered", "mean_not_offered", "SMD", "rate_spread_across_deciles"])
    lines.append(tA.round(4).to_string(index=False))
    for c in ["region_id", "t", "status"]:
        r = A.groupby(c).discount_flag.mean()
        lines.append(f"offer rate by {c}: min {r.min():.4f}  max {r.max():.4f}")
    for m in [2, 3, 4, 5, 10]:
        r = A.groupby(A.customer_id % m).discount_flag.mean()
        lines.append(f"offer rate by customer_id mod {m}: min {r.min():.4f}  max {r.max():.4f}")
    # does being offered last season predict being offered now, within the same customer?
    ct = pd.crosstab(A.l_discount, A.discount_flag, normalize="index")
    lines.append("P(offer now | offered last season):\n" + ct.round(4).to_string())
    covA = [c for c in covs if c != "tenure"]
    jt = joint_test(A, "discount_flag", covA)
    lines.append(f"Joint test (covariates | sub-region+season FE): F={jt['F_cov']:.2f}, p={jt['p_cov']:.3g}, "
                 f"R2 increment from covariates={jt['R2_cov_increment']:.2e}, full R2={jt['R2_full']:.2e}")
    lines.append(f"Joint test of sub-region+season FE alone: F={jt['F_fe']:.2f}, p={jt['p_fe']:.3g}")
    lines.append(f"AUC of fitted assignment model = {auc(A.discount_flag.to_numpy(), jt['fitted']):.4f}  (0.5 = no predictive power)")

    # ---------------- B. DEPTH ----------------
    B = d[d.discount_flag == 1].dropna(subset=[c for c in covs if c not in ("l_discount",)]).copy()
    lines.append(f"\nB. DEPTH among discounted (n={len(B):,}); mean $ off = {B.off.mean():.4f}")
    lines.append("depth shares by status:\n" + pd.crosstab(B.status, B.off, normalize="index").round(4).to_string())
    t2 = []
    for c in covs + CUR_EXPOSURE:
        x5, x1 = B.loc[B.off == 5, c].dropna(), B.loc[B.off == 1, c].dropna()
        corr = B[[c, "off"]].dropna().corr().iloc[0, 1]
        t2.append((c, B.loc[B.off == 1, c].mean(), B.loc[B.off == 5, c].mean(), smd(x5, x1), corr))
    tB = pd.DataFrame(t2, columns=["covariate", "mean_$1_off", "mean_$5_off", "SMD_5_vs_1", "corr_with_depth"])
    lines.append(tB.round(4).to_string(index=False))
    for c in ["region_id", "t", "status"]:
        chi2, p, dof, _ = stats.chi2_contingency(pd.crosstab(B[c], B.off))
        lines.append(f"chi-square depth x {c}: chi2={chi2:.1f}, dof={dof}, p={p:.3g}")
    Bm = B.dropna(subset=["l_off"])
    Bm = Bm[Bm.l_discount == 1]
    chi2, p, dof, _ = stats.chi2_contingency(pd.crosstab(Bm.l_off, Bm.off))
    lines.append(f"chi-square depth x last-season depth: chi2={chi2:.1f}, dof={dof}, p={p:.3g}")
    covB = [c for c in covs if c != "l_discount"]
    jt = joint_test(B, "off", covB)
    lines.append(f"Joint test (covariates | FE): F={jt['F_cov']:.2f}, p={jt['p_cov']:.3g}, "
                 f"R2 increment={jt['R2_cov_increment']:.2e}, full R2={jt['R2_full']:.2e}")
    lines.append(f"Joint test of sub-region+season FE alone: F={jt['F_fe']:.2f}, p={jt['p_fe']:.3g}")

    txt = "\n".join(lines)
    print(txt)
    open(f"{out_dir}/01_randomization_checks.txt", "w").write(txt)
    tA.to_csv(f"{out_dir}/01_balance_eligibility.csv", index=False)
    tB.to_csv(f"{out_dir}/01_balance_depth.csv", index=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
