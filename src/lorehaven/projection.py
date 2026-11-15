"""project(policy, rates): follow 1,000 new prospects quarter by quarter under a pricing policy.

Each quarter, for each group of people:
  new members     = prospects x (sign-up rate at the price they are offered)
  members kept    = members   x (stay rate for their tenure at the price they pay)
  revenue         = everyone who pays x the price they pay
Every rate is LOOKED UP in the observed $12-era tables (rates.py): there are no fitted curves. So the policy may only
use prices that were actually tested: the $12 base, $0-$5 off for prospects and $1-$5 off for members (every member
had an offer in the data, so members at full price were never observed).

Groups tracked, separately for engaged podcast listeners (high_podcast) and everyone else (low_podcast):
  never members, former members, and members by tenure: first renewal, second renewal, established (third renewal on).
Reads its rates from outputs/results/metrics.json, so the tool needs only Flask (no pandas).
"""
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

BASE_PRICE = 12
PODCAST_SEGMENTS = ("high_podcast", "low_podcast")
TENURE_GROUPS = ("first_renewal", "second_renewal", "established")
TODAYS_DEPTHS = (1, 2, 3, 4, 5)      # today's engine: a random $1-$5 off
SEGMENT_NAME = {("high_podcast", "never"): "warm_listener", ("low_podcast", "never"): "cold",
                ("high_podcast", "lapsed"): "win_back", ("low_podcast", "lapsed"): "lapsed_low_podcast"}
METRICS_PATH = Path(__file__).resolve().parents[2] / "outputs" / "results" / "metrics.json"


# Inputs:  a Policy, and the observed rate tables read from outputs/results/metrics.json
# Outputs: per-quarter members and revenue, summary numbers and warnings (returned; no files written)


@dataclass
class Policy:
    offer_share: dict = field(default_factory=lambda: {"high_podcast": 0.25, "low_podcast": 0.25})   # 0-1
    prospect_discount: dict = field(default_factory=lambda: {"high_podcast": 3, "low_podcast": 3})  # whole $, 0-5
    new_member_discount: int = 3            # $ off at a member's first and second renewal (1-5)
    established_member_discount: int = 3    # $ off from the third renewal on (1-5)
    win_back_offers: bool = True            # False = former members see only the list price
    todays_random_depths: bool = False      # True = today's engine: random $1-$5 for offered prospects and all members
    horizon_quarters: int = 12
    starting_prospects: int = 1000
    discount_rate_per_quarter: float = 0.0


@dataclass
class Rates:
    signup: dict                 # (segment name, $ off) -> sign-up rate
    stay: dict                   # (podcast segment, tenure group, price) -> stay rate
    share_high_podcast: float    # engaged listeners' share of never-member prospects
    tested_offer_share: float    # share of prospects who got an offer in the data (25%)


class InvalidPolicy(ValueError):
    """Raised for invalid inputs; .field names the Policy field to fix."""
    def __init__(self, message, field=None):
        """Store the message and the name of the input that caused it."""
        super().__init__(message)
        self.field = field


def load_rates(metrics_path: Path = METRICS_PATH) -> Rates:
    """Read the rate tables from metrics.json (single source of truth)."""
    metrics = json.loads(Path(metrics_path).read_text())
    value = lambda key: metrics[key]["value"]
    signup = {(segment, off): value(f"rates.signup.{segment}.off{off}") for segment in SEGMENT_NAME.values() for off in range(6)}
    stay = {(segment, group, price): value(f"rates.stay.{segment}.{group}.price{price}")
            for segment in PODCAST_SEGMENTS for group in TENURE_GROUPS for price in range(BASE_PRICE - 5, BASE_PRICE)}
    return Rates(signup, stay, value("projection.share_high_podcast"), value("projection.tested_offer_share"))


def _whole_dollars(name, label, x, low, high):
    """Raise InvalidPolicy unless x is a whole number of dollars from low to high (only tested prices allowed)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x != int(x) or not low <= x <= high:
        raise InvalidPolicy(f"{label} must be a whole number of dollars from ${low} to ${high} (got {x!r}): "
                            f"those are the discounts tested in the data.", name)


def validate(policy: Policy) -> None:
    """Raise InvalidPolicy with a plain-language message for any input outside what the data tested."""
    for name in ("win_back_offers", "todays_random_depths"):
        if not isinstance(getattr(policy, name), bool):
            raise InvalidPolicy("Win-back offers and today's random discounts must be on or off.", name)
    for segment in PODCAST_SEGMENTS:
        share = policy.offer_share.get(segment)
        if isinstance(share, bool) or not isinstance(share, (int, float)) or not math.isfinite(share) or not 0 <= share <= 1:
            raise InvalidPolicy(f"Offer share must be between 0% and 100% (got {share!r}).", f"offer_share.{segment}")
        _whole_dollars(f"prospect_discount.{segment}", "Prospect discount", policy.prospect_discount.get(segment), 0, 5)
    _whole_dollars("new_member_discount", "New-member discount", policy.new_member_discount, 1, 5)
    _whole_dollars("established_member_discount", "Established-member discount", policy.established_member_discount, 1, 5)
    if isinstance(policy.horizon_quarters, bool) or not isinstance(policy.horizon_quarters, int) or not 1 <= policy.horizon_quarters <= 40:
        raise InvalidPolicy(f"Horizon must be a whole number of quarters from 1 to 40 (got {policy.horizon_quarters!r}).", "horizon_quarters")
    if isinstance(policy.starting_prospects, bool) or not isinstance(policy.starting_prospects, int) or policy.starting_prospects < 1:
        raise InvalidPolicy("Starting prospects must be a whole number of at least 1.", "starting_prospects")
    rate = policy.discount_rate_per_quarter
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or not 0 <= rate < 1:
        raise InvalidPolicy(f"Quarterly discount rate must be from 0% to below 100% (got {rate!r}).", "discount_rate_per_quarter")


def prospect_offers(policy: Policy, segment: str, status: str) -> list:
    """(share of these prospects, $ off) pairs: who gets which offer. status is 'never' or 'lapsed'."""
    share = policy.offer_share[segment]
    if status == "lapsed" and not policy.win_back_offers:
        return [(1.0, 0)]
    if policy.todays_random_depths:
        return [(share / len(TODAYS_DEPTHS), off) for off in TODAYS_DEPTHS] + [(1 - share, 0)]
    return [(share, int(policy.prospect_discount[segment])), (1 - share, 0)]


def member_offers(policy: Policy, tenure_group: str) -> list:
    """(share of these members, $ off) pairs for a tenure group."""
    if policy.todays_random_depths:
        return [(1 / len(TODAYS_DEPTHS), off) for off in TODAYS_DEPTHS]
    off = policy.established_member_discount if tenure_group == "established" else policy.new_member_discount
    return [(1.0, int(off))]


def warnings_for(policy: Policy, rates: Rates) -> list:
    """Plain-language caution when a setting reaches beyond what the data can vouch for."""
    if any(policy.offer_share[s] > rates.tested_offer_share + 0.005 for s in PODCAST_SEGMENTS):
        return [f"In the data about {rates.tested_offer_share:.0%} of prospects got an offer. Offering more people assumes each "
                f"person responds the same when everyone gets one: confirm it with a randomized holdout."]
    return []


def _one_quarter(policy, rates, people, segment) -> dict:
    """Move one podcast segment forward one quarter. Updates `people` in place and returns the quarter's flows."""
    flow = dict(members_start=sum(people[g] for g in TENURE_GROUPS), new_members=0.0, revenue=0.0, discount_cost=0.0,
                discounted_payers=0.0)
    joined = {}
    for status in ("never", "lapsed"):
        joined[status] = 0.0
        for share, off in prospect_offers(policy, segment, status):
            joiners = people[status] * share * rates.signup[SEGMENT_NAME[segment, status], off]
            joined[status] += joiners
            flow["revenue"] += joiners * (BASE_PRICE - off)
            flow["discount_cost"] += joiners * off
            flow["discounted_payers"] += joiners if off else 0.0
    kept = {}
    for group in TENURE_GROUPS:
        kept[group] = 0.0
        for share, off in member_offers(policy, group):
            stayers = people[group] * share * rates.stay[segment, group, BASE_PRICE - off]
            kept[group] += stayers
            flow["revenue"] += stayers * (BASE_PRICE - off)
            flow["discount_cost"] += stayers * off
            flow["discounted_payers"] += stayers if off else 0.0
    flow["churned"] = flow["members_start"] - sum(kept.values())
    flow["new_members"] = joined["never"] + joined["lapsed"]
    people["never"] -= joined["never"]
    people["lapsed"] += flow["churned"] - joined["lapsed"]
    people["established"] = kept["second_renewal"] + kept["established"]
    people["second_renewal"] = kept["first_renewal"]
    people["first_renewal"] = flow["new_members"]
    return flow


def project(policy: Policy, rates: Rates) -> dict:
    """Run the policy quarter by quarter. Returns per-quarter totals, summary numbers and warnings."""
    validate(policy)
    share = {"high_podcast": rates.share_high_podcast, "low_podcast": 1 - rates.share_high_podcast}
    people = {s: {"never": policy.starting_prospects * share[s], "lapsed": 0.0, **{g: 0.0 for g in TENURE_GROUPS}}
              for s in PODCAST_SEGMENTS}
    quarters = []
    for quarter in range(1, policy.horizon_quarters + 1):
        total = dict(quarter=quarter, members_start=0.0, new_members=0.0, churned=0.0, revenue=0.0, discount_cost=0.0,
                     discounted_payers=0.0)
        for segment in PODCAST_SEGMENTS:
            for key, amount in _one_quarter(policy, rates, people[segment], segment).items():
                total[key] += amount
        total["members"] = sum(people[s][g] for s in PODCAST_SEGMENTS for g in TENURE_GROUPS)
        quarters.append(total)

    per_1000 = 1000 / policy.starting_prospects
    present_value = lambda q: q["revenue"] / (1 + policy.discount_rate_per_quarter) ** (q["quarter"] - 1)
    member_quarters = sum(q["members"] for q in quarters)
    renewals_due = sum(q["members_start"] for q in quarters)
    summary = {
        "revenue_per_1000_prospects": per_1000 * sum(present_value(q) for q in quarters),
        "first_quarter_revenue_per_1000": per_1000 * quarters[0]["revenue"],
        "members_at_end_per_1000": per_1000 * quarters[-1]["members"],
        "average_revenue_per_member_quarter": sum(q["revenue"] for q in quarters) / member_quarters if member_quarters else 0.0,
        "average_quarterly_churn": sum(q["churned"] for q in quarters) / renewals_due if renewals_due else 0.0,
        "discount_cost_per_1000": per_1000 * sum(q["discount_cost"] for q in quarters),
        "share_of_member_quarters_discounted": sum(q["discounted_payers"] for q in quarters) / member_quarters if member_quarters else 0.0,
    }
    return {"quarters": quarters, "summary": summary, "warnings": warnings_for(policy, rates)}
