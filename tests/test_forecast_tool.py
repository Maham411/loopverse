"""Forecast tool contract (SPEC section 5) and the made-up coverage trap."""
from datetime import date

import pandas as pd
import pytest

from smogguard import config as C
from smogguard.forecast_tool import covered_areas, forecast, supported_dates

KEYS = {"location", "target_date", "pm25", "hazardous", "status", "source"}


def test_exact_schema_ok():
    r = forecast("Gulberg", "2026-10-29")
    assert set(r) == KEYS and r["status"] == "ok" and r["source"] == "team_model"
    assert isinstance(r["pm25"], float) and isinstance(r["hazardous"], bool)
    row = pd.read_csv(C.PREDICTIONS_CSV).query("sensor_id == 'S01' and target_date == '2026-10-29'")
    assert r["pm25"] == round(float(row["predicted_pm25"].iloc[0]), 2)


@pytest.mark.parametrize("loc,area", [("gulberg", "Gulberg"), ("Defence", "DHA"), ("S07", "Allama Iqbal Town"),
                                      ("iqbal town", "Allama Iqbal Town"), ("  Walled City ", "Walled City")])
def test_aliases_and_sensor_ids(loc, area):
    r = forecast(loc, "2026-11-01")
    assert r["status"] == "ok" and r["location"] == area


@pytest.mark.parametrize("loc,day", [("Karachi", "2026-10-29"), ("Delhi", "2026-10-29"), ("Anarkali", "2026-10-29"),
                                     ("Gulberg", "2026-12-15"), ("Gulberg", "2026-10-28"), ("Gulberg", "tomorrow"),
                                     ("Gulberg", "2026-13-45"), (None, "2026-10-29"), ("Gulberg", None)])
def test_unsupported_never_guesses(loc, day):
    r = forecast(loc, day)
    assert set(r) == KEYS and r["status"] == "unavailable" and r["pm25"] is None and r["hazardous"] is None


def test_date_objects_and_coverage_lists():
    assert forecast("DHA", date(2026, 11, 7))["status"] == "ok"
    assert len(covered_areas()) == 15
    assert supported_dates() == [f"2026-10-{d}" for d in (29, 30, 31)] + [f"2026-11-0{d}" for d in range(1, 8)]
