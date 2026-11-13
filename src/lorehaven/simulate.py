"""simulate(policy, model): members, revenue, LTV and guardrails for a pricing policy.

State per podcast segment, per quarter:
  never      prospects who have never been members
  lapsed     former members (eligible to re-join)
  members    current members
Each quarter:
  join probability  = sum over the price mix of  share x logistic(intercept[status] + slope x price)
  stay probability  = sum over the member price mix of share x logistic(retention_intercept + retention_slope x price)
  new members pay the price they joined at; continuing members pay the member price.
LTV = sum over quarters of revenue / (1 + discount_rate) ** (quarter - 1), reported per 1,000 starting prospects.

Model parameters come from outputs/results/metrics.json (see load_model). Nothing here is fitted.
"""
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

SEGMENTS = ("high_podcast", "low_podcast")
TESTED_PROSPECT_PRICE_RANGE = (7, 15)   # prices observed for prospects
TESTED_MEMBER_PRICE_RANGE = (7, 14)     # members in discounting regions were always discounted
RANDOM_DEPTHS = (1, 2, 3, 4, 5)         # today's engine: depth drawn uniformly from $1-$5
METRICS_PATH = Path(__file__).resolve().parents[2] / "outputs" / "results" / "metrics.json"


@dataclass
class PricingPolicy:
    base_price: float = 12.0
    offer_share: dict = field(default_factory=lambda: {"high_podcast": 0.25, "low_podcast": 0.25})  # 0..1
    prospect_discount: dict = field(default_factory=lambda: {"high_podcast": 3.0, "low_podcast": 3.0})  # $ off
    member_discount: float = 3.0            # $ off for every continuing member
    lapsed_get_offers: bool = True          # False = former members only see the base price (no win-back offer)
    random_depths: bool = False             # True = today's engine (uniform $1-$5) for prospects and members
    horizon_quarters: int = 12
    starting_prospects: int = 1000
    discount_rate_per_quarter: float = 0.0


@dataclass
class SegmentModel:
    share_of_prospects: float
    join_never_intercept: float
    join_never_price_slope: float
    join_lapsed_intercept: float
    join_lapsed_price_slope: float
    stay_intercept: float
    stay_price_slope: float


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def load_model(metrics_path: Path = METRICS_PATH) -> dict:
    """Build per-segment model parameters from metrics.json (single source of truth)."""
    metrics = json.loads(Path(metrics_path).read_text())
    value = lambda key: metrics[key]["value"]
    model = {}
    for segment in SEGMENTS:
        prefix = f"simulator.{segment}."
        model[segment] = SegmentModel(**{name: value(prefix + name) for name in SegmentModel.__dataclass_fields__})
    return model


def member_value(segment_model: SegmentModel, member_price: float, horizon_quarters=None) -> float:
    """Expected revenue from one current member who is charged member_price every quarter.
      stay = logistic(stay_intercept + stay_price_slope * member_price)
      finite horizon H:  sum_{k=1..H} member_price * stay**k
      horizon None:      member_price * stay / (1 - stay)   (steady state, members never age out)
    """
    stay = logistic(segment_model.stay_intercept + segment_model.stay_price_slope * member_price)
    if horizon_quarters is None:
        return member_price * stay / (1 - stay)
    return member_price * sum(stay ** k for k in range(1, horizon_quarters + 1))


def validate_policy(policy: PricingPolicy) -> None:
    """Raise ValueError with a plain-language message for any invalid input."""
    def number(name, x):
        if isinstance(x, bool) or not isinstance(x, (int, float)) or math.isnan(x):
            raise ValueError(f"{name} must be a number (got {x!r}).")
    number("Base price", policy.base_price)
    if not 1 <= policy.base_price <= 50:
        raise ValueError(f"Base price must be between $1 and $50 (got ${policy.base_price}).")
    for segment in SEGMENTS:
        if segment not in policy.offer_share or segment not in policy.prospect_discount:
            raise ValueError(f"Missing settings for segment '{segment}'.")
        share, discount = policy.offer_share[segment], policy.prospect_discount[segment]
        number(f"Offer share ({segment})", share)
        number(f"Prospect discount ({segment})", discount)
        if not 0 <= share <= 1:
            raise ValueError(f"Offer share for {segment} must be between 0% and 100% (got {share:.0%}).")
        if not 0 <= discount < policy.base_price:
            raise ValueError(f"Prospect discount for {segment} must be at least $0 and below the base price "
                             f"${policy.base_price} (got ${discount}).")
    number("Member discount", policy.member_discount)
    if not 0 <= policy.member_discount < policy.base_price:
        raise ValueError(f"Member discount must be at least $0 and below the base price ${policy.base_price} "
                         f"(got ${policy.member_discount}).")
    if policy.random_depths and policy.base_price - max(RANDOM_DEPTHS) <= 0:
        raise ValueError("With random $1-$5 depths the base price must be above $5.")
    if not isinstance(policy.lapsed_get_offers, bool) or not isinstance(policy.random_depths, bool):
        raise ValueError("Win-back offers and random depths must be on/off (True/False).")
    if not isinstance(policy.horizon_quarters, int) or not 1 <= policy.horizon_quarters <= 40:
        raise ValueError(f"Horizon must be a whole number of quarters from 1 to 40 (got {policy.horizon_quarters}).")
    if not isinstance(policy.starting_prospects, int) or policy.starting_prospects <= 0:
        raise ValueError(f"Starting prospects must be a positive whole number (got {policy.starting_prospects}).")
    number("Discount rate", policy.discount_rate_per_quarter)
    if not 0 <= policy.discount_rate_per_quarter < 1:
        raise ValueError(f"Quarterly discount rate must be from 0% to below 100% (got {policy.discount_rate_per_quarter:.0%}).")


def prospect_price_mix(policy: PricingPolicy, segment: str, status: str = "never") -> list:
    """List of (share of prospects, price) pairs for never-members or lapsed members."""
    share, base = policy.offer_share[segment], policy.base_price
    if status == "lapsed" and not policy.lapsed_get_offers:
        return [(1.0, base)]
    if policy.random_depths:
        offered = [(share / len(RANDOM_DEPTHS), base - d) for d in RANDOM_DEPTHS]
    else:
        offered = [(share, base - policy.prospect_discount[segment])]
    return offered + [(1 - share, base)]


def member_price_mix(policy: PricingPolicy) -> list:
    if policy.random_depths:
        return [(1 / len(RANDOM_DEPTHS), policy.base_price - d) for d in RANDOM_DEPTHS]
    return [(1.0, policy.base_price - policy.member_discount)]


def range_warnings(policy: PricingPolicy) -> list:
    warnings = []
    low, high = TESTED_PROSPECT_PRICE_RANGE
    for segment in SEGMENTS:
        for share, price in prospect_price_mix(policy, segment):
            if share > 0 and not low <= price <= high:
                warnings.append(f"Prospect price ${price:g} ({segment.replace('_', ' ')}) is outside the tested "
                                f"${low}-${high} range: results are an extrapolation.")
    low, high = TESTED_MEMBER_PRICE_RANGE
    for share, price in member_price_mix(policy):
        if not low <= price <= high:
            warnings.append(f"Member price ${price:g} is outside the tested ${low}-${high} range "
                            f"(members were always discounted): results are an extrapolation.")
    return sorted(set(warnings))


def simulate(policy: PricingPolicy, model: dict) -> dict:
    validate_policy(policy)
    members_price_mix = member_price_mix(policy)
    quarters = []
    state = {s: {"never": policy.starting_prospects * model[s].share_of_prospects, "lapsed": 0.0, "members": 0.0}
             for s in SEGMENTS}
    for quarter in range(1, policy.horizon_quarters + 1):
        totals = dict(quarter=quarter, new_members=0.0, churned=0.0, members=0.0, revenue=0.0,
                      discount_cost=0.0, members_start=0.0, discounted_payers=0.0)
        for segment in SEGMENTS:
            m, s = model[segment], state[segment]
            joined, joined_revenue, joined_discount, joined_discounted = {}, 0.0, 0.0, 0.0
            for status, intercept, slope in (("never", m.join_never_intercept, m.join_never_price_slope),
                                             ("lapsed", m.join_lapsed_intercept, m.join_lapsed_price_slope)):
                joined[status] = 0.0
                for share, price in prospect_price_mix(policy, segment, status):
                    joiners = s[status] * share * logistic(intercept + slope * price)
                    joined[status] += joiners
                    joined_revenue += joiners * price
                    joined_discount += joiners * (policy.base_price - price)
                    joined_discounted += joiners if price < policy.base_price else 0.0
            stayers, stay_revenue, stay_discount = 0.0, 0.0, 0.0
            for share, price in members_price_mix:
                stay = s["members"] * share * logistic(m.stay_intercept + m.stay_price_slope * price)
                stayers += stay
                stay_revenue += stay * price
                stay_discount += stay * (policy.base_price - price)
            churned = s["members"] - stayers
            new_members = joined["never"] + joined["lapsed"]
            totals["members_start"] += s["members"]
            s["never"] -= joined["never"]
            s["lapsed"] += churned - joined["lapsed"]
            s["members"] = stayers + new_members
            totals["new_members"] += new_members
            totals["churned"] += churned
            totals["members"] += s["members"]
            totals["revenue"] += joined_revenue + stay_revenue
            totals["discount_cost"] += joined_discount + stay_discount
            totals["discounted_payers"] += joined_discounted + (stayers if stay_discount > 0 else 0.0)
        quarters.append(totals)

    per_thousand = 1000 / policy.starting_prospects
    discounting = [(1 + policy.discount_rate_per_quarter) ** (q["quarter"] - 1) for q in quarters]
    member_quarters = sum(q["members"] for q in quarters)
    churn_base = sum(q["members_start"] for q in quarters)
    kpis = {
        "ltv_per_1000_prospects": per_thousand * sum(q["revenue"] / f for q, f in zip(quarters, discounting)),
        "first_quarter_revenue_per_1000": per_thousand * quarters[0]["revenue"],
        "members_at_end_per_1000": per_thousand * quarters[-1]["members"],
        "average_revenue_per_member_quarter": sum(q["revenue"] for q in quarters) / member_quarters if member_quarters else 0.0,
        "average_quarterly_churn": sum(q["churned"] for q in quarters) / churn_base if churn_base else 0.0,
        "discount_cost_per_1000": per_thousand * sum(q["discount_cost"] for q in quarters),
        "share_of_member_quarters_discounted": sum(q["discounted_payers"] for q in quarters) / member_quarters if member_quarters else 0.0,
    }
    return {"quarters": quarters, "kpis": kpis, "warnings": range_warnings(policy)}
