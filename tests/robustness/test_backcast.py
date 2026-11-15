"""APPENDIX: backtest of the fitted-curve simulator against 2017-2019 member counts.

The reported errors live in outputs/robustness/metrics.json (written by `python -m lorehaven.robustness`). These tests check
that they are present and within stated bounds. The full re-run is opt-in
(set LOREHAVEN_RUN_SLOW=1): it needs the raw CSVs and about 4-5 GB of RAM."""
import json
import math
import os

import pytest

from lorehaven import data_prep
from lorehaven.robustness.curve_simulator import METRICS_PATH

METRICS = json.loads(METRICS_PATH.read_text())
RUNS = ("in_sample", "out_of_sample_same_season", "out_of_sample_avg_2018")


def raw_data_available() -> bool:
    try:
        return (data_prep.data_dir() / "customer_panel.csv").exists()
    except FileNotFoundError:
        return False


@pytest.mark.parametrize("run", RUNS)
def test_backcast_errors_are_reported(run):
    for stat in ("mape", "mape_treated", "mape_panem", "total_error_q11_pct"):
        value = METRICS[f"backcast.{run}.{stat}"]["value"]
        assert math.isfinite(value)


def test_in_sample_replay_tracks_actual_members():
    # accounting check: replaying the fitted history should land close to the actual end-2019 member total
    assert abs(METRICS["backcast.in_sample.total_error_q11_pct"]["value"]) < 0.05
    assert METRICS["backcast.in_sample.mape_treated"]["value"] < 0.10


def test_out_of_sample_error_is_reported_not_hidden():
    # the honest bound stated in the README: treated regions within ~10% on average, Panem much worse
    assert METRICS["backcast.out_of_sample_avg_2018.mape_treated"]["value"] < 0.15
    assert METRICS["backcast.out_of_sample_avg_2018.mape_panem"]["value"] > METRICS["backcast.out_of_sample_avg_2018.mape_treated"]["value"]


@pytest.mark.skipif(os.environ.get("LOREHAVEN_RUN_SLOW") != "1" or not raw_data_available(),
                    reason="slow: set LOREHAVEN_RUN_SLOW=1 (needs raw CSVs and ~4-5 GB RAM)")
def test_backcast_rerun_matches_metrics():
    from lorehaven import backcast
    summary = backcast.summarize(backcast.run_backcast(data_prep.build_analysis_table()))
    for key, value in summary.items():
        assert value == pytest.approx(METRICS[f"backcast.{key}"]["value"], rel=1e-6)
