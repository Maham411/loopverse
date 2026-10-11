"""Hazardous forecasts: our holdout forecasts are all below 165, so these paths
are exercised with a temporary predictions file containing hazardous values."""
import pandas as pd
import pytest

from smogguard import config as C, forecast_tool
from smogguard.assistant import ask, ask_detailed


@pytest.fixture
def hazardous_predictions(tmp_path, monkeypatch):
    df = pd.read_csv(C.PREDICTIONS_CSV, dtype={"target_date": str})
    def setv(sid, day, v):
        m = (df.sensor_id == sid) & (df.target_date == day)
        df.loc[m, "predicted_pm25"], df.loc[m, "hazardous"] = v, int(v >= 165)
    setv("S01", "2026-10-29", 210.0)   # Gulberg: hazardous two days in a row
    setv("S01", "2026-10-30", 190.0)
    setv("S02", "2026-10-29", 262.0)   # DHA: full school closure level
    path = tmp_path / "predictions.csv"
    df.to_csv(path, index=False)
    monkeypatch.setattr(C, "PREDICTIONS_CSV", path)
    forecast_tool.reload()
    yield
    monkeypatch.undo()
    forecast_tool.reload()


def test_half_day_school_and_hazard_advice(hazardous_predictions):
    r = ask("Will schools in Gulberg close tomorrow?")
    assert "210 µg/m³ PM2.5 — HAZARDOUS" in r["answer"] and "half-day" in r["answer"]
    assert r["forecast_called"] and "DOC-03" in r["sources"]


def test_full_closure(hazardous_predictions):
    r = ask("Should I send my kids to school in DHA tomorrow?")
    assert "full closure" in r["answer"] and "262" in r["answer"]


def test_hazardous_band_guidance(hazardous_predictions):
    r = ask("Is it safe to go outside in Gulberg tomorrow?")
    assert "avoid outdoor activity entirely" in r["answer"] and "DOC-01" in r["sources"]
    assert "100–164" not in r["answer"]


def test_odd_even_consecutive_days_checked(hazardous_predictions):
    r, d = ask_detailed("Will the odd-even rule apply in Gulberg tomorrow?")
    assert "Odd-even is triggered" in r["answer"] and "2 consecutive days" in r["answer"]
    assert r["sources"] == ["DOC-05"]
    assert d["tool_calls"] >= 3  # target day plus neighbouring days were checked


def test_odd_even_single_day_not_triggered(hazardous_predictions):
    r = ask("Will odd-even apply in DHA tomorrow?")
    assert "Odd-even is not triggered yet" in r["answer"]


def test_roman_urdu_hazardous(hazardous_predictions):
    r = ask("Kal Gulberg mein school band honge?")
    assert "KHATARNAK" in r["answer"] and "half-day" in r["answer"]
