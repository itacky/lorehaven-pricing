"""Lorehaven pricing simulator — a thin Flask wrapper around lorehaven.simulate.simulate().

Run:  python app/app.py   (from any folder). It picks a free local port, prints the address and opens it
      in your browser. Choose a port with LOREHAVEN_PORT=8050; skip the browser with LOREHAVEN_NO_BROWSER=1.
Needs only Flask: simulate() uses the standard library and reads outputs/results/metrics.json.
The model is never reimplemented here: inputs are converted to a PricingPolicy, simulate() does the work,
and parameters come from outputs/results/metrics.json via load_model().
"""
import json
import math
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))                              # app/presets.py
sys.path.insert(0, str(APP_DIR.parent / "src"))               # lorehaven package, works without `pip install -e .`
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
    if not math.isfinite(value):                       # 'nan', 'inf', 1e999 ... parse as floats but are not usable
        raise InvalidPolicy(f"{FORM_LABELS[name]} must be an ordinary number (got '{raw}').", name)
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
    """Numbers shown on the page, read from metrics.json (never typed into the HTML)."""
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
        "backcast_same_season_pct": round(100 * value("backcast.out_of_sample_same_season.mape_treated")),
        **answer_facts(value),
    }


def answer_facts(value) -> dict:
    """Numbers for the answer, evidence and limitations sections, formatted for display (all from metrics.json)."""
    pct = lambda key: round(100 * value(key))
    signed = lambda key: f"{100 * value(key):+.0f}%"
    money_k = lambda key: f"${value(key) / 1000:.1f}k"
    uplift = lambda segment: pct(f"uplift.base12.{segment}.incremental_share_at_5")
    stay = lambda segment, tenure: pct(f"fit_check_in_sample.{segment}.member_{tenure}.price11.observed")
    holdout = {arm: pct(f"assumption.holdout_arm_share.{arm}") for arm in ("5_off", "list", "3_off")}
    return {
        "signup_odds_pct": pct("headline.signup_odds_change_per_dollar_off"),
        "retention_odds_pct": pct("headline.retention_odds_change_per_dollar_off"),
        "full_rollout_vs_today": signed("headline.ltv_recommended_vs_today_pct"),
        "full_rollout_vs_today_h40": signed("headline.ltv_recommended_vs_today_pct_h40"),
        "holdout_vs_today": signed("headline.holdout_design_ltv_vs_today_pct"),
        "holdout_vs_today_h40": signed("headline.holdout_design_ltv_vs_today_pct_h40"),
        "holdout_ltv": money_k("headline.holdout_design_ltv_per_1000"),
        "today_ltv": money_k("scenario.status_quo_2019.ltv_per_1000_prospects"),
        "vs_best_uniform": signed("headline.ltv_recommended_vs_best_uniform_pct"),
        "holdout_arms": holdout,
        "first_quarter_today": f"${value('ope.status_quo_random_25pct.first_quarter_revenue'):.2f}",
        "first_quarter_offer_all": f"${value('ope.offer_all_5_off.first_quarter_revenue'):.2f}",
        # who a $5 offer wins: share of $5-offer joiners who would NOT have joined at list price ($12 era)
        "uplift_rows": [
            {"label": "Cold prospects", "detail": "never members, less engaged", "share": uplift("cold"),
             "prospects": pct("uplift.base12.cold.share_of_prospects")},
            {"label": "Former members, less engaged", "detail": "", "share": uplift("lapsed_low_podcast"),
             "prospects": pct("uplift.base12.lapsed_low_podcast.share_of_prospects")},
            {"label": "Warm listeners", "detail": "never members, engaged", "share": uplift("warm_listener"),
             "prospects": pct("uplift.base12.warm_listener.share_of_prospects")},
            {"label": "Win-backs", "detail": "former members, engaged", "share": uplift("win_back"),
             "prospects": pct("uplift.base12.win_back.share_of_prospects")},
        ],
        # who stays at $11: first renewal vs established, observed in the $12 era
        "stay_rows": [
            {"label": "Engaged listeners", "first": stay("high_podcast", "first_renewal"), "established": stay("high_podcast", "established")},
            {"label": "Less engaged", "first": stay("low_podcast", "first_renewal"), "established": stay("low_podcast", "established")},
        ],
        "did_jump": f"{value('event_study.treated_x_q9'):.2f}",
        "did_predicted": f"{value('did.randomized_prediction_delta'):.2f}",
        "tested_offer_share_pct": pct("simulator.tested_offer_share"),
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


PREFERRED_PORTS = (8050, 8765, 8080, 5000)   # 5000 is often reserved on Windows (Hyper-V / WSL / AirPlay)


def find_open_port() -> int:
    """First preferred port the OS lets us bind on 127.0.0.1; otherwise let the OS choose one."""
    requested = os.environ.get("LOREHAVEN_PORT", "").strip()
    if requested and not (requested.isdigit() and 1 <= int(requested) <= 65535):
        print(f"LOREHAVEN_PORT='{requested}' is not a valid port (1-65535); choosing one automatically.")
        requested = ""
    candidates = (int(requested),) if requested else PREFERRED_PORTS
    for port in candidates + (0,):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
                if requested and port == 0:
                    print(f"Port {requested} is not available; using another free port instead.")
                return probe.getsockname()[1]
            except OSError:                    # in use, or forbidden (Windows WinError 10013)
                continue
    raise RuntimeError("Could not find a free local port.")


def main():
    app = create_app()
    port = find_open_port()
    url = f"http://127.0.0.1:{port}"
    print(f"\nLorehaven pricing simulator is running at {url}  (press Ctrl+C to stop)\n", flush=True)
    if not os.environ.get("LOREHAVEN_NO_BROWSER"):
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
