"""Follow-up to 02: (1) are radio/display decile patterns driven by score distributions shifting by year?
(2) best single cutoff for the scores that matter.  Imports model helpers from 02.
Usage: python analysis/02b_thresholds.py <prepared_parquet> <out_dir>"""
import sys, importlib.util
import numpy as np, pandas as pd
spec = importlib.util.spec_from_file_location("m02", "notebooks/eda/02_price_response_by_propensity.py")
m02 = importlib.util.module_from_spec(spec); spec.loader.exec_module(m02)

d = pd.read_parquet(sys.argv[1]); out = sys.argv[2]
d = d[(d.treated == 1) & (d.t >= 1)].copy()
d["y"] = d.sign_up_flag; d["price"] = d.membership_price.astype(float)
d["region_t"] = d.region_name + "_" + d.t.astype(str)
A = d[d.status.isin(["never", "lapsed"])]; R = d[d.status == "member"]
L = []
L.append("score means by year (all customers, treated regions):\n" +
         d.groupby("year")[list(m02.SCORES.values()) + ["display_missing"]].mean().round(3).to_string())
for name, df in [("ACQ", A), ("RET", R)]:
    for s in ["radio", "display"]:
        col = m02.SCORES[s]
        rows = []
        for yr, g in df.groupby("year"):
            g = g[g[col] > 0] if s == "display" else g
            if len(g) < 1000: continue
            hi = g[g[col] >= g[col].median()]; lo = g[g[col] < g[col].median()]
            rows.append(dict(year=yr, n=len(g), median=g[col].median(),
                             slope_low_half=100*m02.slope(lo, "region_t")[0], slope_high_half=100*m02.slope(hi, "region_t")[0],
                             y_low=lo.y.mean(), y_high=hi.y.mean()))
        L.append(f"\n{name} {s}: within-year split at median\n" + pd.DataFrame(rows).round(4).to_string(index=False))
grid = np.round(np.arange(0.20, 0.81, 0.025), 3)
for name, df, s in [("ACQ", A, "podcast"), ("ACQ", A, "social"), ("RET", R, "podcast")]:
    r = m02.threshold_search(df, "region_t", m02.SCORES[s], grid)
    r.to_csv(f"{out}/02b_{name}_{s}_threshold.csv", index=False)
    best = r.loc[r.rss.idxmin()]
    L.append(f"\n{name} {s} threshold search: best cutoff = {best.cutoff} (share above = {best.share_high:.3f}); "
             f"slope below = {best.slope_low_pp:.3f} pp/$, above = {best.slope_high_pp:.3f} pp/$")
    L.append(r[["cutoff","share_high","slope_low_pp","slope_high_pp","delta_rss_vs_best"]].round(4).to_string(index=False))
# fine-grained podcast view (20 bins) for ACQ
t = m02.by_decile(A, "region_t", m02.SCORES["podcast"], nbins=20)
L.append("\nACQ podcast, 20 bins:\n" + t[["decile","score_lo","score_hi","mean_y","slope_pp_per_dollar","se_pp"]].round(4).to_string(index=False))
# 2x2 segments: podcast x social
for name, df in [("ACQ", A), ("RET", R)]:
    rows = []
    for pk, pg in df.groupby(df.customer_podcast_score >= 0.5):
        for sk, g in pg.groupby(pg.customer_social_score >= 0.5):
            b, se = m02.slope(g, "region_t")
            rows.append(dict(podcast_ge_05=pk, social_ge_05=sk, n=len(g), share=len(g)/len(df), mean_y=g.y.mean(),
                             slope_pp=100*b, se_pp=100*se, elasticity=b*g.price.mean()/g.y.mean()))
    L.append(f"\n{name} segments podcast>=0.5 x social>=0.5:\n" + pd.DataFrame(rows).round(4).to_string(index=False))
txt = "\n".join(L); open(f"{out}/02b_thresholds.txt", "w").write(txt); print(txt)
