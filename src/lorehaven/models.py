"""Price-response models, DiD / event study, uplift by segment, and off-policy evaluation.

Identification (stated once, referenced by every estimate):
  RANDOMIZED: inside the discounting regions, whether a prospect gets an offer (25%) and the depth
  ($1-$5, uniform) are randomized (brief + balance checks). Members are always offered a discount
  and the depth is randomized. Comparing customers in the same region x quarter therefore gives
  causal price effects. Panem has no price variation and only pins its own fixed effects.
  DiD: the $12 base cut is compared with Panem; requires parallel trends with a single control region.

All standard errors are clustered by customer.
"""
import numpy as np
import pandas as pd
import scipy.sparse as sp
import statsmodels.api as sm
from scipy import stats

CLUSTER_COLUMN = "customer_id"


# ---------------------------------------------------------------- generic estimators
def _fixed_effect_dummies(frame: pd.DataFrame, fixed_effect_columns: list) -> pd.DataFrame:
    """First FE column gets a full set of dummies (no constant); later FE columns drop one level."""
    parts = [pd.get_dummies(frame[fixed_effect_columns[0]].astype(str), prefix="fe0", dtype=float)]
    for i, col in enumerate(fixed_effect_columns[1:], start=1):
        parts.append(pd.get_dummies(frame[col].astype(str), prefix=f"fe{i}", drop_first=True, dtype=float))
    return pd.concat(parts, axis=1)


def fit_logit_clustered(data: pd.DataFrame, outcome: str, regressors: list, fixed_effect_columns: list,
                        cluster_column: str = CLUSTER_COLUMN) -> dict:
    """Logit with fixed effects, fitted on collapsed cells (identical MLE to row-level), with
    cluster-robust sandwich standard errors (default: by customer) computed from row-level scores.

      P(outcome = 1) = 1 / (1 + exp(-(fixed effects + sum_j coef_j * regressor_j)))
    """
    keys = fixed_effect_columns + regressors
    cells = data.groupby(keys, observed=True)[outcome].agg(successes="sum", trials="size").reset_index()
    design = pd.concat([_fixed_effect_dummies(cells, fixed_effect_columns), cells[regressors].astype(float)], axis=1)
    fit = sm.GLM(np.column_stack([cells.successes, cells.trials - cells.successes]), design,
                 family=sm.families.Binomial()).fit()
    cells["predicted"] = fit.predict(design)

    # bread: Fisher information summed over cells = sum_c trials_c * p_c (1 - p_c) x_c x_c'
    X = design.to_numpy()
    weights = (cells.trials * cells.predicted * (1 - cells.predicted)).to_numpy()
    information_inverse = np.linalg.inv(X.T @ (X * weights[:, None]))

    # meat: per-customer sums of row scores (y - p) * x
    rows = data[list(dict.fromkeys([cluster_column, outcome] + keys))].merge(cells[keys + ["predicted"]], on=keys, how="left")
    residual = rows[outcome].to_numpy(float) - rows.predicted.to_numpy()
    customer_codes, n_clusters = pd.factorize(rows[cluster_column])[0], rows[cluster_column].nunique()
    names = list(design.columns)
    column_position = {name: i for i, name in enumerate(names)}
    score_rows, score_cols, score_values = [], [], []
    for i, fe_col in enumerate(fixed_effect_columns):        # FE score = residual summed per customer x level
        level_names = (f"fe{i}_" + rows[fe_col].astype(str)).to_numpy()
        sums = pd.DataFrame({"c": customer_codes, "level": level_names, "r": residual}).groupby(["c", "level"]).r.sum().reset_index()
        sums = sums[sums.level.isin(column_position)]        # dropped reference levels have no column
        score_rows.append(sums.c.to_numpy()); score_cols.append(sums.level.map(column_position).to_numpy())
        score_values.append(sums.r.to_numpy())
    for regressor in regressors:                               # regressor score = residual * x summed per customer
        sums = pd.Series(residual * rows[regressor].to_numpy(float)).groupby(customer_codes).sum()
        score_rows.append(sums.index.to_numpy()); score_cols.append(np.full(len(sums), column_position[regressor]))
        score_values.append(sums.to_numpy())
    cluster_scores = sp.csr_matrix((np.concatenate(score_values), (np.concatenate(score_rows), np.concatenate(score_cols))),
                                   shape=(n_clusters, len(names)))
    meat = (cluster_scores.T @ cluster_scores).toarray() * n_clusters / (n_clusters - 1)
    covariance = information_inverse @ meat @ information_inverse

    reg_index = [names.index(r) for r in regressors]
    fixed_effects = pd.Series(fit.params.values[:-len(regressors)], index=design.columns[:-len(regressors)])
    fixed_effects.index = fixed_effects.index.str.replace("fe0_", "", regex=False)
    return {
        "coef": pd.Series(fit.params.values[reg_index], index=regressors),
        "se_clustered": pd.Series(np.sqrt(np.diag(covariance))[reg_index], index=regressors),
        "se_naive": pd.Series(fit.bse.values[reg_index], index=regressors),
        "covariance": pd.DataFrame(covariance[np.ix_(reg_index, reg_index)], index=regressors, columns=regressors),
        "fixed_effects": fixed_effects, "cells": cells, "n_rows": len(rows), "n_clusters": n_clusters,
    }


def fit_linear_fe_clustered(data: pd.DataFrame, outcome: str, regressors: list, fixed_effect_column: str) -> dict:
    """Linear probability model with one set of fixed effects (within transformation),
    customer-clustered standard errors."""
    columns = [outcome] + regressors
    demeaned = data[columns].astype(float) - data.groupby(fixed_effect_column, observed=True)[columns].transform("mean")
    X, y = demeaned[regressors].to_numpy(), demeaned[outcome].to_numpy()
    xtx_inverse = np.linalg.inv(X.T @ X)
    coef = xtx_inverse @ X.T @ y
    residual = y - X @ coef
    cluster_scores = pd.DataFrame(X * residual[:, None]).groupby(data[CLUSTER_COLUMN].to_numpy()).sum().to_numpy()
    n_clusters = len(cluster_scores)
    covariance = xtx_inverse @ (cluster_scores.T @ cluster_scores) @ xtx_inverse * n_clusters / (n_clusters - 1)
    return {"coef": pd.Series(coef, index=regressors), "se_clustered": pd.Series(np.sqrt(np.diag(covariance)), index=regressors),
            "covariance": pd.DataFrame(covariance, index=regressors, columns=regressors),
            "n_rows": len(data), "n_clusters": n_clusters}


def wald_test(result: dict, terms: list) -> dict:
    """Joint test that all listed coefficients are zero, using the clustered covariance."""
    b = result["coef"][terms].to_numpy()
    V = result["covariance"].loc[terms, terms].to_numpy()
    statistic = float(b @ np.linalg.solve(V, b))
    return {"chi2": statistic, "df": len(terms), "p_value": float(stats.chi2.sf(statistic, len(terms)))}


# ---------------------------------------------------------------- populations
def prospects(table: pd.DataFrame, treated_only=False) -> pd.DataFrame:
    """Keep rows for prospects (not a member last quarter), optionally in the discounting regions only."""
    rows = table[table.is_prospect == 1]
    return rows[rows.is_treated_region == 1] if treated_only else rows


def members(table: pd.DataFrame, treated_only=False) -> pd.DataFrame:
    """Keep rows for members who could renew this quarter, optionally in the discounting regions only."""
    rows = table[table.status == "member"]
    return rows[rows.is_treated_region == 1] if treated_only else rows


def _with_price(rows: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of the rows with the price paid or offered as a float 'price' column."""
    rows = rows.copy()
    rows["price"] = rows.membership_price.astype(float)
    return rows


# ---------------------------------------------------------------- price-response models
def acquisition_model(table, with_lapsed=False, fixed_effects=("region_quarter",), treated_only=False):
    """Sign-up probability of prospects vs price; with_lapsed adds a former-member intercept shift.
    Fit per podcast segment by passing a segment-filtered table (each segment gets its own fixed effects;
    a pooled price x segment interaction with shared fixed effects was misspecified - see decision log)."""
    rows = _with_price(prospects(table, treated_only))
    regressors = ["price", "is_lapsed"] if with_lapsed else ["price"]
    return fit_logit_clustered(rows, "sign_up_flag", regressors, list(fixed_effects))


def retention_model(table, fixed_effects=("region_quarter",), treated_only=False):
    """Probability a member stays vs price."""
    rows = _with_price(members(table, treated_only))
    return fit_logit_clustered(rows, "stayed", ["price"], list(fixed_effects))


def segment_models(table) -> dict:
    """Separate fits per podcast segment: sign-up for never-members, sign-up for lapsed members,
    and retention, each with its own price slope and region x quarter fixed effects.
    (A shared-FE interaction model mis-predicted lapsed and low-podcast customers - see decision log.)"""
    fits = {}
    for segment, flag in (("high_podcast", 1), ("low_podcast", 0)):
        segment_rows = table[table.is_high_podcast == flag]
        fits[segment] = {"join_never": acquisition_model(segment_rows[segment_rows.is_lapsed == 0]),
                         "join_lapsed": acquisition_model(segment_rows[segment_rows.is_lapsed == 1]),
                         "retention": retention_model(segment_rows)}
    return fits


CURRENT_REGIME_QUARTERS = (9, 10, 11)   # 2019 spring-fall: $12 base outside Panem
TENURE_GROUPS = {"first_renewal": (1, 1), "second_renewal": (2, 2), "established": (3, 99)}  # quarters as member


def current_regime_rows(table) -> pd.DataFrame:
    """Keep discounting-region rows from the $12 era (quarters 9-11) used to calibrate the simulator."""
    rows = table[(table.is_treated_region == 1) & table.quarter_index.isin(CURRENT_REGIME_QUARTERS)].copy()
    rows["current_regime"] = "q9_q11"
    return rows


def simulator_fits(table) -> dict:
    """Average-quarter response curves for the simulator, fit on the current $12 regime (treated regions,
    quarters 9-11) WITHOUT quarter fixed effects. Offers and depths are randomized with the same
    probabilities in every quarter, so price is independent of quarter and this logit estimates the
    curve averaged over the three quarters (what a 'typical quarter' simulator needs).
    Retention is fit separately by member tenure (first renewal, second renewal, established).
    Fixed-effect models above remain the main elasticity estimates."""
    rows = current_regime_rows(table)
    fixed = ("current_regime",)
    fits = {}
    for segment, flag in (("high_podcast", 1), ("low_podcast", 0)):
        segment_rows = rows[rows.is_high_podcast == flag]
        never = segment_rows[(segment_rows.is_prospect == 1) & (segment_rows.is_lapsed == 0)]
        fits[segment] = {"join_never": acquisition_model(never, fixed_effects=fixed),
                         "join_lapsed": acquisition_model(segment_rows[segment_rows.is_lapsed == 1], fixed_effects=fixed)}
        for group, (low, high) in TENURE_GROUPS.items():
            tenure_rows = segment_rows[segment_rows.member_tenure.between(low, high)]
            fits[segment][f"stay_{group}"] = retention_model(tenure_rows, fixed_effects=fixed)
    prospects_now = rows[(rows.is_prospect == 1) & (rows.is_lapsed == 0)]
    fits["share_high_podcast_among_never_prospects"] = prospects_now.is_high_podcast.mean()
    fits["tested_prospect_price_range"] = (int(rows[rows.is_prospect == 1].membership_price.min()),
                                           int(rows[rows.is_prospect == 1].membership_price.max()))
    fits["tested_member_price_range"] = (int(rows[rows.status == "member"].membership_price.min()),
                                         int(rows[rows.status == "member"].membership_price.max()))
    return fits


def pull_forward_check(table) -> dict:
    """Does a deeper offer this quarter lower NEXT quarter's sign-up among prospects who did not join?
    Linear probability, FE = next quarter's region x quarter, controlling for next quarter's depth
    (both depths are randomized and independent). Negative coefficient = pull-forward / depletion."""
    rows = table[table.is_treated_region == 1].copy()
    by_customer = rows.groupby("customer_id", sort=False)
    rows["next_signup"] = by_customer.sign_up_flag.shift(-1)
    rows["next_depth"] = by_customer.discount_depth.shift(-1).astype(float)
    rows["next_region_quarter"] = by_customer.region_quarter.shift(-1)
    rows["depth_now"] = rows.discount_depth.astype(float)
    rows = rows[(rows.is_prospect == 1) & (rows.sign_up_flag == 0) & rows.next_signup.notna()]
    out = {}
    for segment, flag in (("high_podcast", 1), ("low_podcast", 0)):
        fit = fit_linear_fe_clustered(rows[rows.is_high_podcast == flag], "next_signup", ["depth_now", "next_depth"], "next_region_quarter")
        out[segment] = {"next_quarter_effect_per_dollar_now": fit["coef"]["depth_now"],
                        "next_quarter_effect_se": fit["se_clustered"]["depth_now"],
                        "same_quarter_effect_per_dollar": fit["coef"]["next_depth"]}
    return out


def base_cut_observed_comparison(table) -> pd.DataFrame:
    """DESCRIPTIVE: revenue and members per customer, treated vs Panem, 2019 spring-fall (post-cut)
    vs the same seasons of 2018. Not causal (one control region, failed pre-trend test)."""
    rows = table[table.quarter_index.isin([5, 6, 7, 9, 10, 11])].copy()
    rows["period"] = np.where(rows.quarter_index >= 9, "2019_spring_fall", "2018_spring_fall")
    rows["revenue"] = rows.sign_up_flag * rows.membership_price
    rows["group"] = np.where(rows.is_treated_region == 1, "treated", "panem")
    out = rows.groupby(["group", "period"]).agg(customer_quarters=("customer_id", "size"), members=("sign_up_flag", "sum"),
                                                revenue=("revenue", "sum")).reset_index()
    out["members_per_customer_quarter"] = out.members / out.customer_quarters
    out["revenue_per_customer_quarter"] = out.revenue / out.customer_quarters
    out["revenue_per_member_quarter"] = out.revenue / out.members
    return out


# ---------------------------------------------------------------- 2019 base cut: DiD and event study
def base_cut_did(table) -> dict:
    """DIRECTION CHECK ONLY. Standard errors clustered by sub-region (20 clusters; few-cluster caveat).
    Prospects at LIST price only (no offer), all regions. Treated no-offer prospects are a random
    75% of treated prospects, so they are comparable to Panem prospects (never offered).
      logit P(sign-up) = region FE + quarter FE + delta * treated x post
    """
    rows = prospects(table)
    rows = rows[rows.discount_flag == 0].copy()
    rows["treated_x_post"] = rows.is_treated_region * (rows.quarter_index >= 9)
    # cluster by sub-region (20 clusters, 6 in Panem): customer clustering ignores shared regional shocks
    did = fit_logit_clustered(rows, "sign_up_flag", ["treated_x_post"], ["region_name", "quarter_index"], "region_id")

    reference_quarter = 8   # last quarter before the cut
    event_terms = []
    for q in sorted(rows.quarter_index.unique()):
        if q != reference_quarter:
            name = f"treated_x_q{q}"
            rows[name] = rows.is_treated_region * (rows.quarter_index == q)
            event_terms.append(name)
    event = fit_logit_clustered(rows, "sign_up_flag", event_terms, ["region_name", "quarter_index"], "region_id")
    pre_terms = [t for t in event_terms if int(t.split("_q")[1]) < reference_quarter]
    return {"did": did, "event": event, "pretrend_test": wald_test(event, pre_terms),
            "reference_quarter": reference_quarter}


# ---------------------------------------------------------------- uplift by segment
PROSPECT_SEGMENTS = {  # (is_lapsed, is_high_podcast) -> label
    (1, 1): "win_back", (0, 1): "warm_listener", (1, 0): "lapsed_low_podcast", (0, 0): "cold",
}


def label_segments(rows: pd.DataFrame) -> pd.Series:
    """Name each prospect's segment from whether they are a former member and their podcast engagement."""
    keys = list(zip(rows.is_lapsed, rows.is_high_podcast))
    return pd.Series([PROSPECT_SEGMENTS[k] for k in keys], index=rows.index)


def uplift_by_segment(table, base_price=None) -> pd.DataFrame:
    """Treated prospects. Per segment: list-price sign-up rate p0 (observed) and uplift of each
    $k discount vs list (LPM with region x quarter FE, clustered SEs).
    Decomposition at $5 (ASSUMPTION: nobody is less likely to join because of a discount):
      already_sold = p0, persuadable = uplift_5, out_of_reach = 1 - p0 - uplift_5."""
    rows = prospects(table, treated_only=True).copy()
    if base_price is not None:
        rows = rows[rows.base_price == base_price]
    rows["segment"] = label_segments(rows)
    depth_columns = []
    for k in range(1, 6):
        rows[f"depth_{k}"] = (rows.discount_depth == k).astype(float)
        depth_columns.append(f"depth_{k}")
    output = []
    for segment, group in rows.groupby("segment"):
        fit = fit_linear_fe_clustered(group, "sign_up_flag", depth_columns, "region_quarter")
        p0 = group.loc[group.discount_depth == 0, "sign_up_flag"].mean()
        record = {"segment": segment, "n": len(group), "share_of_prospects": len(group) / len(rows), "p0_list": p0}
        for k in range(1, 6):
            record[f"uplift_{k}"] = fit["coef"][f"depth_{k}"]
            record[f"uplift_{k}_se"] = fit["se_clustered"][f"depth_{k}"]
        record.update(already_sold=p0, persuadable_at_5=record["uplift_5"],
                      out_of_reach_at_5=1 - p0 - record["uplift_5"],
                      incremental_share_at_5=record["uplift_5"] / (p0 + record["uplift_5"]),
                      all_uplifts_non_negative=all(record[f"uplift_{k}"] >= 0 for k in range(1, 6)))
        output.append(record)
    return pd.DataFrame(output)


# ---------------------------------------------------------------- who needs the discount?
def prospect_discount_efficiency(table) -> pd.DataFrame:
    """Treated prospects, by segment x base-price era x depth. Within an era, depth is randomized,
    so raw differences vs the no-offer group are causal (same quarters, same mix).
      signup_rate_k            sign-up rate at $k off (k = 0 is list price)
      incremental_k            signup_rate_k - signup_rate_0           (persuaded by the discount)
      already_sold_share_k     signup_rate_0 / signup_rate_k           (joiners who did not need it)
      revenue_per_prospect_k   signup_rate_k x price                   (first quarter)
      discount_to_already_sold_per_1000 = k x signup_rate_0 x 1000     ($ handed to people who would join anyway)
      discount_per_incremental_joiner   = k x signup_rate_k / incremental_k
    """
    rows = prospects(table, treated_only=True).copy()
    rows["segment"] = label_segments(rows)
    cells = rows.groupby(["segment", "base_price", "discount_depth"]).agg(
        n=("sign_up_flag", "size"), signup_rate=("sign_up_flag", "mean")).reset_index()
    list_rate = cells[cells.discount_depth == 0].set_index(["segment", "base_price"]).signup_rate
    cells["list_rate"] = [list_rate[(s, b)] for s, b in zip(cells.segment, cells.base_price)]
    cells["price"] = cells.base_price - cells.discount_depth
    cells["incremental"] = cells.signup_rate - cells.list_rate
    cells["already_sold_share"] = cells.list_rate / cells.signup_rate
    cells["revenue_per_prospect"] = cells.signup_rate * cells.price
    cells["discount_to_already_sold_per_1000"] = cells.discount_depth * cells.list_rate * 1000
    cells["discount_per_incremental_joiner"] = np.where(
        cells.discount_depth > 0, cells.discount_depth * cells.signup_rate / cells.incremental, np.nan)
    best = cells.loc[cells.groupby(["segment", "base_price"]).revenue_per_prospect.idxmax()]
    cells["is_revenue_best_depth"] = cells.index.isin(best.index)
    return cells


def member_discount_efficiency(table) -> pd.DataFrame:
    """Treated members (always discounted, depth randomized) by podcast segment x era x price.
      stay_rate                   observed share who stay at that price
      stay_rate_at_shallowest     stay rate at $1 off (highest price observed in the era): members who
                                  stay even with the smallest discount ('already staying')
      extra_stayers_vs_shallowest stay_rate - stay_rate_at_shallowest (bought by the deeper discount)
      revenue_per_member          stay_rate x price (one quarter)
    """
    rows = members(table, treated_only=True)
    cells = rows.groupby(["is_high_podcast", "base_price", "membership_price"]).agg(
        n=("stayed", "size"), stay_rate=("stayed", "mean")).reset_index()
    shallowest = cells.loc[cells.groupby(["is_high_podcast", "base_price"]).membership_price.idxmax()]
    shallow_rate = shallowest.set_index(["is_high_podcast", "base_price"]).stay_rate
    cells["stay_rate_at_shallowest"] = [shallow_rate[(h, b)] for h, b in zip(cells.is_high_podcast, cells.base_price)]
    cells["extra_stayers_vs_shallowest"] = cells.stay_rate - cells.stay_rate_at_shallowest
    cells["revenue_per_member"] = cells.stay_rate * cells.membership_price
    cells["segment"] = np.where(cells.is_high_podcast == 1, "high_podcast", "low_podcast")
    return cells


# ---------------------------------------------------------------- off-policy evaluation
def logging_propensities(rows: pd.DataFrame) -> pd.Series:
    """Empirical probability of each action (0 = no offer, k = $k off) under the logged random policy."""
    return rows.discount_depth.value_counts(normalize=True).sort_index()


def evaluate_policy(rows: pd.DataFrame, policy: dict, propensities: pd.Series) -> dict:
    """Inverse-propensity estimate of the value of a deterministic policy (segment -> depth).
      V(policy) = (1/n) sum_i outcome_i * 1[action_i == policy(segment_i)] / propensity(action_i)
    Outcomes: sign-up, and first-quarter revenue = sign-up x price paid. Customer-clustered SEs."""
    chosen_action = rows.segment.map(policy)
    weight = (rows.discount_depth == chosen_action) / rows.discount_depth.map(propensities)
    result = {}
    for name, outcome in {"signup_rate": rows.sign_up_flag, "first_quarter_revenue": rows.sign_up_flag * rows.membership_price}.items():
        contribution = (outcome * weight).to_numpy(float)
        value = contribution.mean()
        per_customer = pd.Series(contribution - value).groupby(rows.customer_id.to_numpy()).sum()
        n_clusters = len(per_customer)
        se = np.sqrt((per_customer ** 2).sum() * n_clusters / (n_clusters - 1)) / len(rows)
        result[name] = value
        result[name + "_se"] = se
    result["matched_rows"] = int((rows.discount_depth == chosen_action).sum())
    return result


def _on_policy_value(rows) -> dict:
    """Mean outcome under the logged policy, with customer-clustered SE."""
    result = {}
    for name, outcome in {"signup_rate": rows.sign_up_flag, "first_quarter_revenue": rows.sign_up_flag * rows.membership_price}.items():
        values = outcome.to_numpy(float)
        per_customer = pd.Series(values - values.mean()).groupby(rows.customer_id.to_numpy()).sum()
        n = len(per_customer)
        result[name] = values.mean()
        result[name + "_se"] = np.sqrt((per_customer ** 2).sum() * n / (n - 1)) / len(rows)
    result["matched_rows"] = len(rows)
    return result


TARGETING_POLICIES = {
    "no_offers": {s: 0 for s in PROSPECT_SEGMENTS.values()},
    "offer_all_3_off": {s: 3 for s in PROSPECT_SEGMENTS.values()},
    "offer_all_5_off": {s: 5 for s in PROSPECT_SEGMENTS.values()},
    "high_podcast_only_5_off": {"win_back": 5, "warm_listener": 5, "lapsed_low_podcast": 0, "cold": 0},
    "targeted_depth": {"win_back": 4, "warm_listener": 5, "lapsed_low_podcast": 4, "cold": 5},
}


def off_policy_evaluation(table) -> pd.DataFrame:
    """First-quarter (myopic) policy values for prospects in the current $12 regime (q9-q11).
    Multi-quarter value comes from simulate(), not from here."""
    rows = prospects(current_regime_rows(table)).copy()
    rows["segment"] = label_segments(rows)
    propensities = logging_propensities(rows)
    output = [{"policy": "status_quo_random_25pct", **_on_policy_value(rows)}]
    for name, policy in TARGETING_POLICIES.items():
        output.append({"policy": name, **evaluate_policy(rows, policy, propensities)})
    return pd.DataFrame(output), propensities
