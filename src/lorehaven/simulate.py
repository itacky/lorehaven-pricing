"""simulate(policy, model): members, revenue, LTV and guardrails for a pricing policy.

State per podcast segment, per quarter:
  never              prospects who have never been members
  lapsed             former members (eligible to re-join)
  members by tenure  first_renewal (joined last quarter), second_renewal, established (3+ quarters)
Each quarter:
  join probability  = sum over the price mix of share x logistic(intercept[status] + slope[status] x price)
  stay probability  = sum over the member price mix of share x logistic(intercept[tenure] + slope[tenure] x price)
  new members pay the price they joined at; renewing members pay the member price for their tenure group
  (new_member_discount for first and second renewals, established_member_discount afterwards).
LTV = sum over quarters of revenue / (1 + discount_rate) ** (quarter - 1), reported per 1,000 starting prospects.

Model parameters come from outputs/results/metrics.json (see load_model). Nothing here is fitted.
"""
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

SEGMENTS = ("high_podcast", "low_podcast")
TENURE_GROUPS = ("first_renewal", "second_renewal", "established")
RANDOM_DEPTHS = (1, 2, 3, 4, 5)         # today's engine: depth drawn uniformly from $1-$5
METRICS_PATH = Path(__file__).resolve().parents[2] / "outputs" / "results" / "metrics.json"


@dataclass
class PricingPolicy:
    base_price: float = 12.0
    offer_share: dict = field(default_factory=lambda: {"high_podcast": 0.25, "low_podcast": 0.25})  # 0..1
    prospect_discount: dict = field(default_factory=lambda: {"high_podcast": 3.0, "low_podcast": 3.0})  # $ off
    new_member_discount: float = 3.0        # $ off at a member's first and second renewal
    established_member_discount: float = 3.0  # $ off from the third renewal on (members who mostly stay anyway)
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
    stay_first_renewal_intercept: float
    stay_first_renewal_price_slope: float
    stay_second_renewal_intercept: float
    stay_second_renewal_price_slope: float
    stay_established_intercept: float
    stay_established_price_slope: float

    def stay_probability(self, tenure_group: str, price: float) -> float:
        return logistic(getattr(self, f"stay_{tenure_group}_intercept") + getattr(self, f"stay_{tenure_group}_price_slope") * price)


@dataclass
class SimulatorModel:
    segments: dict                          # segment name -> SegmentModel
    calibrated_base_price: float            # base price of the data the curves were fit on
    tested_prospect_prices: tuple           # (min, max) prospect prices in that data
    tested_member_prices: tuple             # (min, max) member prices in that data
    tested_offer_share: float               # share of prospects offered a discount in that data


class InvalidPolicy(ValueError):
    """Raised for invalid inputs; .field names the PricingPolicy field to fix."""
    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def load_model(metrics_path: Path = METRICS_PATH) -> SimulatorModel:
    """Build the simulator model from metrics.json (single source of truth)."""
    metrics = json.loads(Path(metrics_path).read_text())
    value = lambda key: metrics[key]["value"]
    segments = {s: SegmentModel(**{name: value(f"simulator.{s}.{name}") for name in SegmentModel.__dataclass_fields__})
                for s in SEGMENTS}
    return SimulatorModel(segments=segments, calibrated_base_price=value("simulator.calibrated_base_price"),
                          tested_prospect_prices=(value("simulator.tested_prospect_price_min"), value("simulator.tested_prospect_price_max")),
                          tested_member_prices=(value("simulator.tested_member_price_min"), value("simulator.tested_member_price_max")),
                          tested_offer_share=value("simulator.tested_offer_share"))


def member_value(segment_model: SegmentModel, member_price: float, horizon_quarters=None) -> float:
    """Expected revenue from one ESTABLISHED member charged member_price every quarter.
      stay = established retention at that price
      finite horizon H:  sum_{k=1..H} member_price * stay**k
      horizon None:      member_price * stay / (1 - stay)   (steady state; ignores that churners can re-join)
    """
    stay = segment_model.stay_probability("established", member_price)
    if horizon_quarters is None:
        return member_price * stay / (1 - stay)
    return member_price * sum(stay ** k for k in range(1, horizon_quarters + 1))


def _require_number(field_name, label, x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise InvalidPolicy(f"{label} must be a number (got {x!r}).", field_name)


def _require_whole_number(field_name, label, x, low, high):
    if isinstance(x, bool) or not isinstance(x, int) or not low <= x <= high:
        raise InvalidPolicy(f"{label} must be a whole number from {low} to {high} (got {x!r}).", field_name)


def validate_policy(policy: PricingPolicy) -> None:
    """Raise InvalidPolicy with a plain-language message for any invalid input."""
    for name in ("lapsed_get_offers", "random_depths"):
        if not isinstance(getattr(policy, name), bool):
            raise InvalidPolicy("Win-back offers and random depths must be on or off (True/False).", name)
    _require_number("base_price", "Base price", policy.base_price)
    if not 1 <= policy.base_price <= 50:
        raise InvalidPolicy(f"Base price must be between $1 and $50 (got ${policy.base_price:g}).", "base_price")
    for segment in SEGMENTS:
        if segment not in policy.offer_share or segment not in policy.prospect_discount:
            raise InvalidPolicy(f"Missing settings for segment '{segment}'.", "offer_share")
        share, discount = policy.offer_share[segment], policy.prospect_discount[segment]
        _require_number(f"offer_share.{segment}", f"Offer share ({segment})", share)
        _require_number(f"prospect_discount.{segment}", f"Prospect discount ({segment})", discount)
        if not 0 <= share <= 1:
            raise InvalidPolicy(f"Offer share for {segment.replace('_', ' ')} must be between 0% and 100% "
                                f"(got {share:.0%}).", f"offer_share.{segment}")
        if not 0 <= discount < policy.base_price:
            raise InvalidPolicy(f"Prospect discount for {segment.replace('_', ' ')} must be at least $0 and below the "
                                f"base price ${policy.base_price:g} (got ${discount:g}).", f"prospect_discount.{segment}")
    for name, label in (("new_member_discount", "New-member discount"), ("established_member_discount", "Established-member discount")):
        discount = getattr(policy, name)
        _require_number(name, label, discount)
        if not 0 <= discount < policy.base_price:
            raise InvalidPolicy(f"{label} must be at least $0 and below the base price ${policy.base_price:g} "
                                f"(got ${discount:g}).", name)
    if policy.random_depths and policy.base_price <= max(RANDOM_DEPTHS):
        raise InvalidPolicy("With random $1-$5 discounts the base price must be above $5.", "base_price")
    _require_whole_number("horizon_quarters", "Horizon (quarters)", policy.horizon_quarters, 1, 40)
    _require_whole_number("starting_prospects", "Starting prospects", policy.starting_prospects, 1, 10**9)
    _require_number("discount_rate_per_quarter", "Discount rate", policy.discount_rate_per_quarter)
    if not 0 <= policy.discount_rate_per_quarter < 1:
        raise InvalidPolicy(f"Quarterly discount rate must be from 0% to below 100% "
                            f"(got {policy.discount_rate_per_quarter:.0%}).", "discount_rate_per_quarter")


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


def member_price_mix(policy: PricingPolicy, tenure_group: str) -> list:
    if policy.random_depths:
        return [(1 / len(RANDOM_DEPTHS), policy.base_price - d) for d in RANDOM_DEPTHS]
    discount = policy.established_member_discount if tenure_group == "established" else policy.new_member_discount
    return [(1.0, policy.base_price - discount)]


def range_warnings(policy: PricingPolicy, model: SimulatorModel) -> list:
    warnings = []
    if policy.base_price != model.calibrated_base_price:
        warnings.append(f"The model is calibrated at the ${model.calibrated_base_price:g} base price. Other base prices "
                        f"are an extrapolation: discounts and list-price changes may not have the same effect.")
    if any(policy.offer_share[s] > model.tested_offer_share + 0.005 for s in SEGMENTS):
        warnings.append(f"Offers reached about {model.tested_offer_share:.0%} of prospects in the data. Wider coverage assumes each "
                        f"person responds the same when everyone gets an offer; test it with a randomized holdout.")
    low, high = model.tested_prospect_prices
    for segment in SEGMENTS:
        for status in ("never", "lapsed"):
            for share, price in prospect_price_mix(policy, segment, status):
                if share > 0 and not low <= price <= high:
                    warnings.append(f"Prospect price ${price:g} is outside the tested ${low:g}-${high:g} range: "
                                    f"results are an extrapolation.")
    low, high = model.tested_member_prices
    for share, price in member_price_mix(policy, "first_renewal") + member_price_mix(policy, "established"):
        if price >= policy.base_price:
            warnings.append("Members paying the full base price were never observed (every member got a discount): "
                            "results are an extrapolation.")
        elif not low <= price <= high:
            warnings.append(f"Member price ${price:g} is outside the tested ${low:g}-${high:g} range: "
                            f"results are an extrapolation.")
    return sorted(set(warnings))


def _start_state(policy: PricingPolicy, model: SimulatorModel) -> dict:
    return {s: {"never": policy.starting_prospects * model.segments[s].share_of_prospects, "lapsed": 0.0,
                **{g: 0.0 for g in TENURE_GROUPS}} for s in SEGMENTS}


def _advance_segment(policy, segment_model, segment_state, segment) -> dict:
    """One quarter for one segment. Mutates segment_state; returns this quarter's flows."""
    flow = dict(new_members=0.0, churned=0.0, revenue=0.0, discount_cost=0.0, discounted_payers=0.0,
                members_start=sum(segment_state[g] for g in TENURE_GROUPS))
    joined = {}
    for status in ("never", "lapsed"):
        intercept = getattr(segment_model, f"join_{status}_intercept")
        slope = getattr(segment_model, f"join_{status}_price_slope")
        joined[status] = 0.0
        for share, price in prospect_price_mix(policy, segment, status):
            joiners = segment_state[status] * share * logistic(intercept + slope * price)
            joined[status] += joiners
            flow["revenue"] += joiners * price
            flow["discount_cost"] += joiners * (policy.base_price - price)
            flow["discounted_payers"] += joiners if price < policy.base_price else 0.0
    stayed = {}
    for group in TENURE_GROUPS:
        stayed[group] = 0.0
        for share, price in member_price_mix(policy, group):
            stayers = segment_state[group] * share * segment_model.stay_probability(group, price)
            stayed[group] += stayers
            flow["revenue"] += stayers * price
            flow["discount_cost"] += stayers * (policy.base_price - price)
            flow["discounted_payers"] += stayers if price < policy.base_price else 0.0
    flow["churned"] = flow["members_start"] - sum(stayed.values())
    flow["new_members"] = joined["never"] + joined["lapsed"]
    segment_state["never"] -= joined["never"]
    segment_state["lapsed"] += flow["churned"] - joined["lapsed"]
    segment_state["established"] = stayed["second_renewal"] + stayed["established"]
    segment_state["second_renewal"] = stayed["first_renewal"]
    segment_state["first_renewal"] = flow["new_members"]
    return flow


def simulate(policy: PricingPolicy, model: SimulatorModel) -> dict:
    validate_policy(policy)
    state = _start_state(policy, model)
    quarters = []
    for quarter in range(1, policy.horizon_quarters + 1):
        totals = dict(quarter=quarter, new_members=0.0, churned=0.0, revenue=0.0, discount_cost=0.0,
                      discounted_payers=0.0, members_start=0.0)
        for segment in SEGMENTS:
            flow = _advance_segment(policy, model.segments[segment], state[segment], segment)
            for key in flow:
                totals[key] += flow[key]
        totals["members"] = sum(state[s][g] for s in SEGMENTS for g in TENURE_GROUPS)
        quarters.append(totals)

    per_thousand = 1000 / policy.starting_prospects
    discount_factors = [(1 + policy.discount_rate_per_quarter) ** (q["quarter"] - 1) for q in quarters]
    paying_member_quarters = sum(q["members"] for q in quarters)
    churn_base = sum(q["members_start"] for q in quarters)
    total_revenue = sum(q["revenue"] for q in quarters)
    kpis = {
        "ltv_per_1000_prospects": per_thousand * sum(q["revenue"] / f for q, f in zip(quarters, discount_factors)),
        "first_quarter_revenue_per_1000": per_thousand * quarters[0]["revenue"],
        "members_at_end_per_1000": per_thousand * quarters[-1]["members"],
        "average_revenue_per_member_quarter": total_revenue / paying_member_quarters if paying_member_quarters else 0.0,
        "average_quarterly_churn": sum(q["churned"] for q in quarters) / churn_base if churn_base else 0.0,
        "discount_cost_per_1000": per_thousand * sum(q["discount_cost"] for q in quarters),
        "share_of_member_quarters_discounted": (sum(q["discounted_payers"] for q in quarters) / paying_member_quarters
                                                if paying_member_quarters else 0.0),
    }
    return {"quarters": quarters, "kpis": kpis, "warnings": range_warnings(policy, model)}
