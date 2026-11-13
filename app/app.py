"""Lorehaven pricing simulator — a thin Flask wrapper around lorehaven.simulate.simulate().

Run:  python app/app.py   then open http://127.0.0.1:5000
The model is never reimplemented here: inputs are converted to a PricingPolicy, simulate() does the work,
and parameters come from outputs/results/metrics.json via load_model().
"""
import json
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, str(Path(__file__).resolve().parent))      # app/presets.py
from presets import PRESETS, STATUS_QUO                       # noqa: E402

from lorehaven.simulate import METRICS_PATH, InvalidPolicy, PricingPolicy, load_model, simulate  # noqa: E402

# PricingPolicy field -> form input name (so errors can point at the right box)
FORM_FIELD_FOR_POLICY_FIELD = {
    "base_price": "base_price", "offer_share.high_podcast": "offer_share_high", "offer_share.low_podcast": "offer_share_low",
    "prospect_discount.high_podcast": "discount_high", "prospect_discount.low_podcast": "discount_low",
    "new_member_discount": "new_member_discount", "established_member_discount": "established_member_discount",
    "horizon_quarters": "horizon_quarters", "discount_rate_per_quarter": "discount_rate_pct",
    "lapsed_get_offers": "lapsed_get_offers", "random_depths": "random_depths",
}
FORM_LABELS = {
    "base_price": "Base price", "offer_share_high": "Engaged listeners offered", "discount_high": "Engaged listeners' discount",
    "offer_share_low": "Other prospects offered", "discount_low": "Other prospects' discount",
    "new_member_discount": "New-member discount", "established_member_discount": "Established-member discount",
    "horizon_quarters": "Horizon", "discount_rate_pct": "Discount rate",
}


def _number(form: dict, name: str, whole=False):
    raw = form.get(name)
    if raw is None or str(raw).strip() == "":
        raise InvalidPolicy(f"{FORM_LABELS[name]} is empty. Enter a number.", name)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise InvalidPolicy(f"{FORM_LABELS[name]} must be a number (got '{raw}').", name)
    if whole:
        if value != int(value):
            raise InvalidPolicy(f"{FORM_LABELS[name]} must be a whole number of quarters (got {raw}).", name)
        return int(value)
    return value


def policy_from_form(form: dict) -> PricingPolicy:
    """Convert tool inputs (%, $, quarters) into a PricingPolicy (shares 0-1, rates 0-1)."""
    return PricingPolicy(
        base_price=_number(form, "base_price"),
        offer_share={"high_podcast": _number(form, "offer_share_high") / 100, "low_podcast": _number(form, "offer_share_low") / 100},
        prospect_discount={"high_podcast": _number(form, "discount_high"), "low_podcast": _number(form, "discount_low")},
        new_member_discount=_number(form, "new_member_discount"),
        established_member_discount=_number(form, "established_member_discount"),
        lapsed_get_offers=bool(form.get("lapsed_get_offers", False)),
        random_depths=bool(form.get("random_depths", False)),
        horizon_quarters=_number(form, "horizon_quarters", whole=True),
        discount_rate_per_quarter=_number(form, "discount_rate_pct") / 100,
    )


def model_facts(metrics_path: Path) -> dict:
    """Numbers shown in the page's assumptions panel, read from metrics.json (never typed into the HTML)."""
    metrics = json.loads(Path(metrics_path).read_text())
    value = lambda key: metrics[key]["value"]
    pull_forward = [abs(value(f"pull_forward.{s}.next_quarter_effect_per_dollar_now") /
                        value(f"pull_forward.{s}.same_quarter_effect_per_dollar")) for s in ("high_podcast", "low_podcast")]
    return {
        "prospect_low": value("simulator.tested_prospect_price_min"), "prospect_high": value("simulator.tested_prospect_price_max"),
        "member_low": value("simulator.tested_member_price_min"), "member_high": value("simulator.tested_member_price_max"),
        "base": value("simulator.calibrated_base_price"),
        "pull_forward_low_pct": round(100 * min(pull_forward)), "pull_forward_high_pct": round(100 * max(pull_forward)),
        "backcast_treated_pct": round(100 * value("backcast.out_of_sample_avg_2018.mape_treated")),
        "backcast_control_pct": round(100 * value("backcast.out_of_sample_avg_2018.mape_panem")),
    }


def create_app(metrics_path=None) -> Flask:
    app = Flask(__name__)
    app.json.sort_keys = False                    # keep preset order (Recommended first)
    metrics_path = Path(metrics_path or METRICS_PATH)
    model = load_model(metrics_path)
    facts = model_facts(metrics_path)

    @app.get("/")
    def index():
        return render_template("index.html", facts=facts)

    @app.get("/api/presets")
    def presets():
        return jsonify(PRESETS)

    @app.post("/api/simulate")
    def run():
        form = request.get_json(silent=True)
        if not isinstance(form, dict):
            return jsonify(error="Send the settings as JSON.", field=None), 400
        try:
            policy = policy_from_form(form)
            scenario = simulate(policy, model)
            baseline_policy = policy_from_form({**STATUS_QUO["values"], "horizon_quarters": policy.horizon_quarters,
                                                "discount_rate_pct": form.get("discount_rate_pct", 0)})
            baseline = simulate(baseline_policy, model)
        except InvalidPolicy as error:
            field = FORM_FIELD_FOR_POLICY_FIELD.get(error.field, error.field)
            message = str(error).replace("high_podcast", "engaged listeners").replace("low podcast", "other prospects")
            return jsonify(error=message, field=field), 400
        return jsonify(scenario=scenario, baseline=baseline)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
