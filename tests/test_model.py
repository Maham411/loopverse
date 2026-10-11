"""Traps 1 and 4: future leakage and misleading accuracy."""
import json

import numpy as np
import pandas as pd
import pytest

from smogguard import config as C
from smogguard.data_pipeline import build_daily, load_weather
from smogguard.model import LAG_FEATURES, fit_ridge, make_features, recursive_forecast, training_frame


@pytest.fixture(scope="module")
def data():
    daily, _ = build_daily(save=False)
    return daily, load_weather(), daily.pivot(index="date", columns="sensor_id", values="pm25")


def test_features_use_only_the_past(data):
    _, weather, pm = data
    target = pd.Timestamp("2026-10-10")
    before = make_features(pm, weather, [target])
    tampered = pm.copy()
    tampered.loc[target:] = 9999.0  # corrupt the target day and everything after it
    after = make_features(tampered, weather, [target])
    pd.testing.assert_frame_equal(before[LAG_FEATURES], after[LAG_FEATURES])


def test_lag1_is_previous_day(data):
    _, weather, pm = data
    X = make_features(pm, weather, [pd.Timestamp("2026-09-15")]).set_index("sensor_id")
    assert np.allclose(X["lag1"], pm.loc["2026-09-14", X.index])
    assert np.allclose(X["roll7"], pm.loc["2026-09-08":"2026-09-14", X.index].mean())


def test_chronological_split_no_shuffle():
    rep = json.loads(C.MODEL_REPORT_JSON.read_text())
    assert rep["split"]["shuffled"] is False
    assert rep["split"]["train_targets"][1] <= C.TRAIN_END < rep["split"]["test_targets"][0]


def test_scaler_fitted_on_training_rows_only(data):
    daily, weather, _ = data
    train = training_frame(daily, weather, pd.Timestamp(C.TRAIN_END))
    model = fit_ridge(train, LAG_FEATURES, 1.0)
    assert np.allclose(model.named_steps["standardscaler"].mean_, train[LAG_FEATURES].mean().values)
    assert train["target_date"].max() <= pd.Timestamp(C.TRAIN_END)


def test_recursive_forecast_ignores_future_observations(data):
    daily, weather, pm = data
    model = fit_ridge(training_frame(daily, weather, pd.Timestamp("2026-10-10")), LAG_FEATURES, 1.0)
    a = recursive_forecast(model, LAG_FEATURES, pm, weather, "2026-10-11", "2026-10-15")
    tampered = pm.copy()
    tampered.loc["2026-10-11":] = 9999.0
    b = recursive_forecast(model, LAG_FEATURES, tampered, weather, "2026-10-11", "2026-10-15")
    pd.testing.assert_frame_equal(a, b)


def test_model_beats_baselines_and_reports_recall():
    rep = json.loads(C.MODEL_REPORT_JSON.read_text())
    ridge = rep["test_october"]["ridge_one_step"]
    base = rep["baselines_october"]
    assert ridge["mae"] < base["persistence_lag1"]["mae"]
    assert ridge["mae"] < base["rolling_mean_7d"]["mae"]
    for k in ("hazardous_recall", "false_alarms", "precision", "hazardous_caught"):
        assert k in ridge
    lazy = base["always_not_hazardous"]
    assert lazy["accuracy"] > 0.95 and lazy["hazardous_caught"] == 0  # accuracy alone is misleading


def test_alarm_calibrated_on_september_and_checked_on_october():
    rep = json.loads(C.MODEL_REPORT_JSON.read_text())
    al = rep["alarm"]
    assert al["threshold"] in C.ALARM_GRID and "2026-10" not in al["chosen_on"]
    best = max(row["f1"] for row in al["selection_table"])
    assert next(r for r in al["selection_table"] if r["alarm_at"] == al["threshold"])["f1"] == best
    # the calibrated alert catches hazardous days the plain 165 rule misses
    assert al["test_october_recursive"]["hazardous_caught"] > al["test_october_recursive_at_165"]["hazardous_caught"]
