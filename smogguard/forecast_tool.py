"""forecast(location, target_date) - the tool the assistant calls (SPEC section 5).

Returns exactly:
  {"location", "target_date", "pm25", "hazardous", "status", "source"}
Unsupported location or date -> status "unavailable", pm25/hazardous None.
It reads the team's own predictions.csv; it never invents a number.
"""
import re
from datetime import date, datetime
from functools import lru_cache

import pandas as pd

from . import config as C


@lru_cache(maxsize=1)
def _metadata():
    return pd.read_csv(C.SENSOR_METADATA, dtype=str)


@lru_cache(maxsize=1)
def _predictions():
    """(table, source). Team model first; organiser reference only as fallback."""
    if C.PREDICTIONS_CSV.exists():
        df, source = pd.read_csv(C.PREDICTIONS_CSV, dtype={"sensor_id": str, "target_date": str}), "team_model"
    elif C.REFERENCE_FORECAST_CSV.exists():
        df, source = pd.read_csv(C.REFERENCE_FORECAST_CSV, dtype={"sensor_id": str, "target_date": str}), "reference_fallback"
    else:
        df, source = pd.DataFrame(columns=["sensor_id", "target_date", "predicted_pm25", "hazardous"]), "team_model"
    return df, source


def reload():
    """Clear caches (used after the pipeline regenerates predictions.csv)."""
    _predictions.cache_clear()
    _metadata.cache_clear()


def covered_areas():
    return list(_metadata()["area"])


def area_to_sensor():
    m = _metadata()
    return dict(zip(m["area"], m["sensor_id"]))


def supported_dates():
    df, _ = _predictions()
    return sorted(df["target_date"].unique().tolist())


def resolve_location(location):
    """Canonical area name for an area name, alias or sensor ID - else None."""
    if not isinstance(location, str):
        return None
    text = re.sub(r"\s+", " ", location.strip().lower())
    meta = _metadata()
    for sid, area in zip(meta["sensor_id"], meta["area"]):
        if text in (sid.lower(), area.lower()):
            return area
    for area, aliases in C.AREA_ALIASES.items():
        if text in aliases:
            return area
    return None


def _normalise_date(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    return None


def forecast(location, target_date):
    df, source = _predictions()
    area = resolve_location(location)
    day = _normalise_date(target_date)
    result = {
        "location": area if area else str(location),
        "target_date": day if day else str(target_date),
        "pm25": None,
        "hazardous": None,
        "status": "unavailable",
        "source": source,
    }
    if area is None or day is None or day not in supported_dates():
        return result
    sensor = area_to_sensor()[area]
    row = df[(df["sensor_id"] == sensor) & (df["target_date"] == day)]
    if len(row) != 1:
        return result
    pm = float(row["predicted_pm25"].iloc[0])
    result.update(pm25=round(pm, 2), hazardous=bool(int(row["hazardous"].iloc[0])), status="ok")
    return result
