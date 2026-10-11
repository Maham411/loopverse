"""Traps 2 and 3: network mismatch and broken values."""
import numpy as np
import pandas as pd
import pytest

from smogguard import config as C
from smogguard.data_pipeline import aqi_to_pm25, build_daily, flatline_mask, pm25_to_aqi, to_local_date


@pytest.fixture(scope="module")
def built():
    return build_daily(save=False)


def test_batch_properties_come_from_metadata(built):
    _, audit = built
    assert audit["batch_properties"]["batch_1"] == {"timezone": "UTC", "unit_type": "PM2.5"}
    assert audit["batch_properties"]["batch_2"] == {"timezone": "PKT", "unit_type": "AQI"}


def test_utc_shifted_to_pakistan_time():
    local, day = to_local_date(pd.Series(["2026-06-30 19:00:00"]), "UTC")
    assert local.iloc[0].hour == 0 and str(day.iloc[0].date()) == "2026-07-01"  # +5h -> next day


def test_both_networks_align_on_same_local_days(built):
    _, audit = built
    a, b = audit["networks"]["batch_1"], audit["networks"]["batch_2"]
    assert a["local_hours_after_alignment"] == [0] and b["local_hours_after_alignment"] == [0]
    assert a["local_date_range"] == b["local_date_range"] == ["2026-07-01", "2026-10-28"]


def test_aqi_conversion_known_breakpoints():
    assert list(aqi_to_pm25([0, 50, 100, 150, 200, 300])) == [0.0, 12.0, 35.4, 55.4, 150.4, 250.4]
    pm = np.array([20.0, 46.9, 72.4, 178.9])
    assert np.allclose(aqi_to_pm25(pm25_to_aqi(pm)), pm, atol=1.2)


def test_networks_agree_after_conversion(built):
    _, audit = built
    assert audit["cross_network"]["mean_abs_diff_ug"] < 1.0
    assert audit["cross_network"]["aqi_exact_match_rate"] > 0.97


def test_sentinels_counted_and_removed(built):
    daily, audit = built
    assert audit["networks"]["batch_1"]["sentinel_minus_999"] == 27
    assert audit["networks"]["batch_2"]["sentinel_minus_999"] == 29
    assert daily["pm25"].min() > 0 and not (daily[["pm25_b1", "pm25_b2"]] == C.SENTINEL).any().any()


def test_flatline_detector_unit():
    assert flatline_mask([1, 2, 2, 2, 3]).tolist() == [False, True, True, True, False]
    assert flatline_mask([1, 2, 2, 3]).tolist() == [False, False, False, False]


def test_s07_flatline_confirmed_and_interpolated(built):
    daily, audit = built
    conf = audit["flatline_confirmed_both_networks"]
    assert len(conf) == 1 and conf[0]["sensor_id"] == "S07"
    assert (conf[0]["start"], conf[0]["end"], conf[0]["stuck_value"]) == ("2026-08-25", "2026-08-27", 71.8)
    s07 = daily[daily.sensor_id == "S07"].set_index("date")["pm25"]
    gap = s07.loc["2026-08-25":"2026-08-27"]
    assert not (gap == 71.8).any()
    lo, hi = sorted([s07.loc["2026-08-24"], s07.loc["2026-08-28"]])
    assert gap.between(lo, hi).all()  # linear interpolation between valid neighbours


def test_complete_daily_table(built):
    daily, audit = built
    assert len(daily) == 15 * 120 and daily["pm25"].notna().all()
    assert not daily.duplicated(["sensor_id", "date"]).any()
    assert audit["final"]["missing_after_cleaning"] == 0
    assert daily["imputed"].sum() == 3
