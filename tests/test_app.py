"""The Flask tool: page loads, presets run, invalid inputs return a clear 400 pointing at the field."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from app import create_app, find_open_port          # noqa: E402
from presets import PRESETS         # noqa: E402

from lorehaven.simulate import METRICS_PATH         # noqa: E402


@pytest.fixture(scope="module")
def client():
    return create_app().test_client()


def test_page_loads_with_numbers_from_metrics(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"{{" not in response.data          # every template value was filled


def test_page_leads_with_the_answer_then_evidence_simulator_and_limits(client):
    page = client.get("/").get_data(as_text=True)
    order = [page.index(f'id="{section}"') for section in ("answer", "evidence", "simulator", "limits")]
    assert order == sorted(order)
    assert "Were the 2017–2019 price changes effective?" in page and "What we recommend" in page


def test_answer_numbers_come_from_metrics(client):
    metrics = json.loads(METRICS_PATH.read_text())
    value = lambda key: metrics[key]["value"]
    page = client.get("/").get_data(as_text=True)
    assert f"+{round(100 * value('headline.signup_odds_change_per_dollar_off'))}%" in page
    assert f"{100 * value('headline.holdout_design_ltv_vs_today_pct'):+.0f}%" in page
    assert f"Randomized holdout: {round(100 * value('assumption.holdout_arm_share.5_off'))}% $5" in page
    ratio = value("headline.holdout_design_ltv_per_1000") / value("scenario.status_quo_2019.ltv_per_1000_prospects")
    assert f"{ratio:.1f}×" in page
    assert f"{round(100 * value('uplift.base12.cold.incremental_share_at_5'))}%" in page


@pytest.mark.parametrize("preset_id", list(PRESETS))
def test_every_preset_runs(client, preset_id):
    response = client.post("/api/simulate", json=PRESETS[preset_id]["values"])
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {"scenario", "baseline"}
    assert body["scenario"]["kpis"]["ltv_per_1000_prospects"] > 0


def test_presets_keep_their_order_with_recommended_first(client):
    assert list(client.get("/api/presets").get_json()) == list(PRESETS)
    assert list(PRESETS)[0] == "recommended"


def test_status_quo_matches_its_own_baseline(client):
    body = client.post("/api/simulate", json=PRESETS["status_quo"]["values"]).get_json()
    assert body["scenario"]["kpis"] == body["baseline"]["kpis"]


@pytest.mark.parametrize("change, field", [
    ({"base_price": "abc"}, "base_price"),
    ({"base_price": ""}, "base_price"),
    ({"offer_share_high": 150}, "offer_share_high"),
    ({"discount_low": 20}, "discount_low"),
    ({"new_member_discount": -1}, "new_member_discount"),
    ({"horizon_quarters": 2.5}, "horizon_quarters"),
    ({"discount_rate_pct": 100}, "discount_rate_pct"),
    # non-finite values parse as floats; they must give a validation error, not a server error
    ({"horizon_quarters": "nan"}, "horizon_quarters"),
    ({"horizon_quarters": "inf"}, "horizon_quarters"),
    ({"horizon_quarters": "-Infinity"}, "horizon_quarters"),
    ({"horizon_quarters": 1e999}, "horizon_quarters"),
    ({"base_price": "nan"}, "base_price"),
    ({"base_price": "inf"}, "base_price"),
    ({"offer_share_low": "nan"}, "offer_share_low"),
    ({"discount_high": "inf"}, "discount_high"),
    ({"new_member_discount": "nan"}, "new_member_discount"),
    ({"discount_rate_pct": "nan"}, "discount_rate_pct"),
])
def test_invalid_input_returns_400_with_field(client, change, field):
    response = client.post("/api/simulate", json={**PRESETS["recommended"]["values"], **change})
    assert response.status_code == 400
    body = response.get_json()
    assert body["field"] == field
    assert body["error"]


def test_non_json_request_is_rejected(client):
    response = client.post("/api/simulate", data="not json", content_type="text/plain")
    assert response.status_code == 400


def test_port_finder_skips_a_port_that_is_taken(monkeypatch):
    import socket
    blocker = socket.socket(); blocker.bind(("127.0.0.1", 0)); blocker.listen()
    taken = blocker.getsockname()[1]
    monkeypatch.setenv("LOREHAVEN_PORT", str(taken))
    port = find_open_port()                       # falls back to an OS-chosen free port
    blocker.close()
    assert port != taken and port > 0
