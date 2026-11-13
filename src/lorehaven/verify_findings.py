"""Re-derive the numeric claims in FINDINGS.md with the src/ code (independent of notebooks/eda).

Usage:  python -m lorehaven.verify_findings
Writes outputs/results/findings_verification.csv: claim | claimed | rederived | tolerance | status | note.
Mismatches are FLAGGED here, never silently corrected in FINDINGS.md.
Samples follow the EDA definitions (quarters >= 1, treated regions) unless a claim says otherwise.
"""
import json

import numpy as np
import pandas as pd

from lorehaven import data_prep, models
from lorehaven.pipeline import RESULTS_DIR

COUNT, RATE, COEF = 0, 0.0005, 0.005   # tolerances: exact counts, 0.05pp for rates, 0.005 for coefficients


def claims(table: pd.DataFrame, aggregate: pd.DataFrame) -> list:
    eda = table[table.quarter_index >= 1]
    treated = eda[eda.is_treated_region == 1]
    prospects = treated[treated.is_prospect == 1]
    members = treated[treated.status == "member"]
    discounted = treated[treated.discount_flag == 1]
    out = []
    add = lambda claim, claimed, rederived, tol, note="": out.append(
        dict(claim=claim, claimed=claimed, rederived=float(rederived), tolerance=tol, note=note))

    # §1 data structure
    add("panel rows", 6121068, len(table), COUNT)
    add("customers", 510089, table.customer_id.nunique(), COUNT)
    add("duplicate customer x quarter keys", 0, table.duplicated(["customer_id", "quarter_index"]).sum(), COUNT)
    add("customers switching region_id", 0, (table.groupby("customer_id").region_id.nunique() > 1).sum(), COUNT)
    panel_members = table.groupby(["region_name", "quarter_index"], observed=True).sign_up_flag.sum().rename("panel").reset_index()
    joined = aggregate.merge(panel_members, on=["region_name", "quarter_index"])
    add("aggregate member_count rows matching panel sums (of 72)", 72, (joined.member_count == joined.panel).sum(), COUNT)
    add("sub-regions", 20, table.region_id.nunique(), COUNT)

    # §2 assignment
    list_prices = table[table.discount_flag == 0].groupby(["region_id", "quarter_index"]).membership_price.unique()
    wrong_base = sum(set(v) != {b} for (r, q), v in list_prices.items()
                     for b in [12 if (q >= 9 and r not in range(6, 12)) else 15])
    add("sub-region x quarter cells whose list price breaks the $15->$12 rule", 0, wrong_base, COUNT)
    add("rows violating price = base - discount ($1-$5)", 0,
        ((table.discount_flag == 1) & ~table.discount_depth.between(1, 5)).sum()
        + ((table.discount_flag == 0) & (table.discount_depth != 0)).sum(), COUNT)
    add("treated members offered a discount (share)", 1.0, members.discount_flag.mean(), RATE)
    add("treated prospect offer rate", 0.2502, prospects.discount_flag.mean(), RATE)
    depth_shares = discounted.discount_depth.value_counts(normalize=True)
    add("min depth share among discounted", 0.199, depth_shares.min(), 0.001)
    add("max depth share among discounted", 0.201, depth_shares.max(), 0.001)
    add("Panem discounted rows", 0, table[table.is_treated_region == 0].discount_flag.sum(), COUNT)
    lag = members.dropna(subset=["last_quarter_discount_depth"])
    lag = lag[lag.last_quarter_discount_depth > 0]
    add("member depth corr with last quarter depth", 0.0009, np.corrcoef(lag.discount_depth, lag.last_quarter_discount_depth)[0, 1], 0.002)

    # §3 data quality (on the raw file, before NaN handling)
    raw = pd.read_csv(data_prep.data_dir() / "aggregate.csv")
    add("Westeros winter TV ratings recorded as 0", 3, ((raw.region_name == "westeros") & (raw.season == "winter") & (raw.tv_ratings == 0)).sum(), COUNT)
    add("display impressions = 0 with spend > 0 (region x quarter)", 18, ((raw.display_impressions == 0) & (raw.display_spend > 0)).sum(), COUNT)
    props = data_prep.load_propensities()
    zero_by_year = props.groupby("year").display_score_missing.mean()
    add("display propensity share exactly 0, 2017", 0.83, zero_by_year[2017], 0.01)
    add("display propensity share exactly 0, 2019", 0.58, zero_by_year[2019], 0.01)

    # §4 / §6 rates by price (base $15 and $12 eras)
    for base, price, claimed in [(15, 15, 0.0346), (15, 10, 0.1733), (12, 12, 0.0598), (12, 7, 0.2522)]:
        cell = prospects[(prospects.base_price == base) & (prospects.membership_price == price)]
        add(f"sign-up rate base ${base} at ${price}", claimed, cell.sign_up_flag.mean(), RATE)
    for base, price, claimed in [(15, 14, 0.7098), (15, 10, 0.8842), (12, 11, 0.8786), (12, 7, 0.9494)]:
        cell = members[(members.base_price == base) & (members.membership_price == price)]
        add(f"retention base ${base} at ${price}", claimed, cell.stayed.mean(), RATE)
    panem_members = eda[(eda.is_treated_region == 0) & (eda.status == "member")]
    add("Panem member retention at $15", 0.6962, panem_members.stayed.mean(), RATE)

    # §6 logits (EDA sample: treated, quarters >= 1)
    add("sign-up logit price coefficient", -0.3656, models.acquisition_model(eda, treated_only=True)["coef"]["price"], COEF)
    add("retention logit price coefficient", -0.2787, models.retention_model(eda, treated_only=True)["coef"]["price"], COEF)
    low = eda[eda.is_high_podcast == 0]
    add("retention price coefficient, podcast < 0.5", -0.084, models.retention_model(low, treated_only=True)["coef"]["price"], COEF,
        "EDA used a pooled price x segment interaction with shared FE; here the segment is fit on its own")
    add("sign-up price coefficient, podcast < 0.5", -0.606, models.acquisition_model(low, treated_only=True)["coef"]["price"], 0.02,
        "EDA used a pooled interaction; here the segment is fit on its own (never + lapsed pooled)")

    # §5 segments (treated prospects, quarters >= 1)
    rows = prospects.copy()
    rows["segment"] = models.label_segments(rows)
    for segment, share, p0 in [("win_back", 0.073, 0.160), ("warm_listener", 0.349, 0.078),
                               ("lapsed_low_podcast", 0.008, 0.054), ("cold", 0.569, 0.003)]:
        group = rows[rows.segment == segment]
        add(f"{segment} share of prospects", share, len(group) / len(rows), 0.001)
        add(f"{segment} list-price sign-up (Already Sold)", p0, group[group.discount_depth == 0].sign_up_flag.mean(), 0.001)

    # §7 DiD (EDA: prospects at list, quarters >= 1, region + quarter FE)
    did = models.base_cut_did(eda)
    add("DiD delta (log-odds)", 0.829, did["did"]["coef"]["treated_x_post"], 0.02)

    # §8 strategy claims tested against outputs/results/metrics.json (direction: +1 / -1)
    metrics = json.loads((RESULTS_DIR / "metrics.json").read_text())
    value = lambda key: metrics[key]["value"]
    best_winback = value("efficiency.prospect.win_back.base12.revenue_best_depth")
    add("win-back first-quarter revenue peaks at $4 off ($12 era)", 4, best_winback, COUNT)
    best_warm = value("efficiency.prospect.warm_listener.base12.revenue_best_depth")
    add("warm-listener first-quarter revenue highest at $5 off ($12 era)", 5, best_warm, COUNT)
    for winback in ("", "no_winback_"):
        deep = value(f"scenario.prospects_5_off_{winback}members_5_off.ltv_per_1000_prospects")
        shallow = value(f"scenario.prospects_5_off_{winback}members_1_off.ltv_per_1000_prospects")
        add(f"strategy #6: deeper member discount raises value (sign of LTV $5 off - $1 off; {winback or 'with_winback_'}offers)",
            1, np.sign(deep - shallow), COUNT,
            "EDA used steady-state V = p r/(1-r); the 12-quarter cohort simulation reverses it")
    return out


def main():
    table = data_prep.build_analysis_table()
    aggregate = pd.read_csv(data_prep.data_dir() / "aggregate.csv")
    aggregate["quarter_index"] = data_prep.quarter_index(aggregate.year, aggregate.season)
    result = pd.DataFrame(claims(table, aggregate))
    result["abs_diff"] = (result.rederived - result.claimed).abs()
    result["status"] = np.where(result.abs_diff <= result.tolerance, "match", "MISMATCH")
    result.to_csv(RESULTS_DIR / "findings_verification.csv", index=False)
    print(result[["claim", "claimed", "rederived", "status", "note"]].to_string(index=False))
    print(f"\n{(result.status == 'match').sum()} match, {(result.status == 'MISMATCH').sum()} mismatch")
    metrics_path = RESULTS_DIR / "metrics.json"
    metrics = json.loads(metrics_path.read_text())
    for name, count in (("n_claims", len(result)), ("n_match", int((result.status == "match").sum())),
                        ("n_mismatch", int((result.status == "MISMATCH").sum()))):
        metrics[f"verification.{name}"] = {"value": count, "unit": "claims", "label": "observed",
                                           "source": "lorehaven.verify_findings", "note": "see findings_verification.csv"}
    metrics_path.write_text(json.dumps(metrics, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
