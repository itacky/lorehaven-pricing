"""Lorehaven pricing tool: a thin Flask wrapper around lorehaven.projection.project().

Run:  python app/app.py   (from any folder). It picks a free local port, prints the address and opens it
      in your browser. Choose a port with LOREHAVEN_PORT=8050; skip the browser with LOREHAVEN_NO_BROWSER=1.
Needs only Flask: project() uses the standard library and reads the observed rate tables in
outputs/results/metrics.json. Nothing is calculated here: form inputs become a Policy, project() does the work.
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

from lorehaven.formatting import percents_summing_to_100  # noqa: E402
from lorehaven.projection import BASE_PRICE, METRICS_PATH, TESTED_BASES, InvalidPolicy, Policy, load_rates, project  # noqa: E402

# Inputs:  browser form values (JSON) and outputs/results/metrics.json
# Outputs: the page, and projection results as JSON

# Policy field -> form input name (so errors can point at the right box)
FORM_FIELD_FOR_POLICY_FIELD = {
    "base_price": "base_price", "offer_share.high_podcast": "offer_share_high", "offer_share.low_podcast": "offer_share_low",
    "prospect_discount.high_podcast": "discount_high", "prospect_discount.low_podcast": "discount_low",
    "new_member_discount": "new_member_discount", "established_member_discount": "established_member_discount",
    "horizon_quarters": "horizon_quarters", "discount_rate_per_quarter": "discount_rate_pct",
    "win_back_offers": "lapsed_get_offers", "todays_random_depths": "random_depths",
    "holdout_list_share": "holdout_list_pct", "holdout_test_share": "holdout_test_pct",
}
FORM_LABELS = {
    "base_price": "Base price", "offer_share_high": "Engaged listeners offered", "discount_high": "Engaged listeners' discount",
    "offer_share_low": "Other prospects offered", "discount_low": "Other prospects' discount",
    "new_member_discount": "New-member discount", "established_member_discount": "Established-member discount",
    "horizon_quarters": "Horizon", "discount_rate_pct": "Discount rate",
    "holdout_list_pct": "Holdout at list price", "holdout_test_pct": "Test arm at $3 off",
}


def _number(form: dict, name: str, whole=False):
    """Read one form value as a number, with a message that names the box when it is empty or not a number."""
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
            raise InvalidPolicy(f"{FORM_LABELS[name]} must be a whole number (got {raw}).", name)
        return int(value)
    return value


def policy_from_form(form: dict) -> Policy:
    """Convert tool inputs (%, whole $, quarters) into a Policy (shares 0-1)."""
    return Policy(
        base_price=_number(form, "base_price", whole=True),
        offer_share={"high_podcast": _number(form, "offer_share_high") / 100, "low_podcast": _number(form, "offer_share_low") / 100},
        prospect_discount={"high_podcast": _number(form, "discount_high", whole=True),
                           "low_podcast": _number(form, "discount_low", whole=True)},
        new_member_discount=_number(form, "new_member_discount", whole=True),
        established_member_discount=_number(form, "established_member_discount", whole=True),
        win_back_offers=bool(form.get("lapsed_get_offers", False)),
        todays_random_depths=bool(form.get("random_depths", False)),
        holdout_list_share=_number(form, "holdout_list_pct") / 100,
        holdout_test_share=_number(form, "holdout_test_pct") / 100,
        horizon_quarters=_number(form, "horizon_quarters", whole=True),
        discount_rate_per_quarter=_number(form, "discount_rate_pct") / 100,
    )


def page_facts(metrics_path: Path) -> dict:
    """Every number shown on the page, read from metrics.json and formatted for display (never typed into the HTML)."""
    metrics = json.loads(Path(metrics_path).read_text())
    value = lambda key: metrics[key]["value"]
    pct = lambda key: round(100 * value(key))
    signed = lambda key: f"{100 * value(key):+.0f}%"
    money_k = lambda key: f"${value(key) / 1000:.1f}k"
    incremental = lambda segment: pct(f"segment.{segment}.incremental_share_at_5")
    stay = lambda segment, tenure: pct(f"rates.stay.base12.{segment}.{tenure}.price11")
    segments = ("cold", "lapsed_low_podcast", "warm_listener", "win_back")
    share_pct = percents_summing_to_100({s: value(f"segment.{s}.share_of_prospects") for s in segments})   # adds to 100
    row = lambda segment, label, detail: {
        "label": label, "detail": detail, "share": incremental(segment), "prospects": share_pct[segment],
        "list_rate": f"{100 * value(f'rates.signup.base12.{segment}.off0'):.1f}%"}
    return {
        "base": BASE_PRICE,
        "base_choices": list(range(TESTED_BASES[0], TESTED_BASES[1] + 1)),
        "recommended_at_15_vs_12": signed("headline.recommended_at_15_vs_12"),
        "signup_at_list": f"{100 * value('rates.by_price.signup.base12.price12'):.0f}%",
        "signup_at_5_off": f"{100 * value('rates.by_price.signup.base12.price7'):.0f}%",
        "cut_after": f"{value('base_cut.quarters_after_above_panem')} of {value('base_cut.quarters_after')}",
        "cut_before": f"{value('base_cut.quarters_before_above_panem')} of {value('base_cut.quarters_before')}",
        "cut_before_total": value("base_cut.quarters_before"), "cut_after_total": value("base_cut.quarters_after"),
        "recommended_vs_today": signed("headline.recommended_vs_today"),
        "recommended_vs_today_h40": signed("headline.recommended_vs_today_h40"),
        "recommended_revenue": money_k("policy.recommended.revenue_per_1000_prospects"),
        "today_revenue": money_k("policy.today.revenue_per_1000_prospects"),
        "recommended_ratio": f"{value('policy.recommended.revenue_per_1000_prospects') / value('policy.today.revenue_per_1000_prospects'):.1f}",
        "vs_best_uniform": signed("headline.recommended_vs_best_single"),
        "holdout_arms": {arm: pct(f"assumption.holdout_arm_share.{arm}") for arm in ("5_off", "list", "3_off")},
        "mde_renewal_pts": f"{100 * value('holdout.mde_renewal_list10_q3'):.0f}",
        "first_quarter_today": f"${value('first_quarter.today'):.2f}",
        "first_quarter_offer_all": f"${value('first_quarter.everyone_5_off'):.2f}",
        "tested_offer_share_pct": pct("projection.tested_offer_share"),
        # who a $5 offer wins: share of $5-offer joiners who would NOT have joined at list price ($12 era)
        "uplift_rows": [row("cold", "Cold prospects", "never members, less engaged"),
                        row("lapsed_low_podcast", "Former members, less engaged", ""),
                        row("warm_listener", "Warm listeners", "never members, engaged"),
                        row("win_back", "Win-backs", "former members, engaged")],
        "uplift_others_low": min(incremental(s) for s in ("lapsed_low_podcast", "warm_listener", "win_back")),
        "uplift_others_high": max(incremental(s) for s in ("lapsed_low_podcast", "warm_listener", "win_back")),
        # who stays at $11: first renewal vs established, observed in the $12 era
        "stay_rows": [
            {"label": "Engaged listeners", "first": stay("high_podcast", "first_renewal"), "established": stay("high_podcast", "established")},
            {"label": "Less engaged", "first": stay("low_podcast", "first_renewal"), "established": stay("low_podcast", "established")},
        ],
    }


def create_app(metrics_path=None) -> Flask:
    """Build the Flask app: the page, the presets and the projection endpoint."""
    app = Flask(__name__)
    app.json.sort_keys = False                    # keep preset order (Recommended first)
    metrics_path = Path(metrics_path or METRICS_PATH)
    rates = load_rates(metrics_path)
    facts = page_facts(metrics_path)

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
            scenario = project(policy, rates)
            baseline_policy = policy_from_form({**STATUS_QUO["values"], "horizon_quarters": policy.horizon_quarters,
                                                "discount_rate_pct": form.get("discount_rate_pct", 0)})
            baseline = project(baseline_policy, rates)
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
    print(f"\nLorehaven pricing tool is running at {url}  (press Ctrl+C to stop)\n", flush=True)
    if not os.environ.get("LOREHAVEN_NO_BROWSER"):
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
