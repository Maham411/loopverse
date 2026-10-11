"""Data preparation for SmogGuard AI.

Order follows the handbook exactly:
  1. parse time  2. align timezone  3. convert units  4. replace invalid readings
  5. handle faults (flatline)  6. aggregate to daily  7. impute remaining gaps

Key facts found during the data audit (see artifacts/data_audit.json):
  * BOTH batch files contain all 15 sensors (120 days each). sensor_metadata.csv
    defines the properties of each batch: batch_1 = UTC + PM2.5,
    batch_2 = Pakistan time (PKT) + AQI. So each area is observed by two networks.
  * batch_1 timestamps are 19:00 UTC = 00:00 PKT on the NEXT day. Skipping the
    timezone conversion would shift every reading by one day.
  * -999 sentinels never occur on the same sensor-day in both networks.
  * S07 (Allama Iqbal Town) is stuck at 71.8 for 2026-08-25..27 in the PM2.5
    network; the AQI network shows the same stuck value (159), so both readings
    are invalid on those days and the gap is linearly interpolated.
"""
import json

import numpy as np
import pandas as pd

from . import config as C


def load_metadata():
    meta = pd.read_csv(C.SENSOR_METADATA, dtype=str)
    meta.columns = [c.strip() for c in meta.columns]
    assert meta["sensor_id"].is_unique and len(meta) == 15, "expected 15 unique sensors"
    return meta


def batch_properties(meta):
    """Return {batch: {"timezone":..., "unit_type":...}} read from the metadata."""
    props = {}
    for batch, grp in meta.groupby("batch"):
        tz = grp["timezone"].unique()
        unit = grp["unit_type"].unique()
        assert len(tz) == 1 and len(unit) == 1, f"{batch} has mixed properties"
        props[batch] = {"timezone": tz[0], "unit_type": unit[0]}
    return props


def aqi_to_pm25(aqi):
    """Invert the US EPA PM2.5 AQI (piecewise linear between breakpoints)."""
    aqi = np.asarray(aqi, dtype=float)
    out = np.interp(aqi, C.AQI_POINTS, C.PM25_POINTS)
    out[np.isnan(aqi)] = np.nan
    return out


def pm25_to_aqi(pm):
    """Forward EPA conversion (used for display and for the cross-network check)."""
    pm = np.asarray(pm, dtype=float)
    out = np.interp(np.clip(pm, 0, 500.4), C.PM25_POINTS, C.AQI_POINTS)
    out[np.isnan(pm)] = np.nan
    return np.round(out)


def to_local_date(timestamps, timezone):
    """Parse timestamps written in `timezone` and return the Pakistan local date."""
    ts = pd.to_datetime(timestamps)
    if timezone.upper() == "UTC":
        local = ts.dt.tz_localize("UTC").dt.tz_convert(C.LOCAL_TZ)
    elif timezone.upper() in ("PKT", "PST", "ASIA/KARACHI"):
        local = ts.dt.tz_localize(C.LOCAL_TZ)
    else:
        raise ValueError(f"Unknown timezone in metadata: {timezone}")
    return local, local.dt.tz_localize(None).dt.normalize()


def flatline_mask(values, min_run=C.FLATLINE_MIN_RUN):
    """True for readings inside a run of >= min_run identical consecutive values."""
    v = pd.Series(values).reset_index(drop=True)
    run_id = (v != v.shift()).cumsum()
    run_len = v.groupby(run_id).transform("size")
    return ((run_len >= min_run) & v.notna()).to_numpy()


def load_network(batch, props, audit):
    """Load one batch file -> sensor_id, date (PKT), pm25 with quality flags."""
    raw = pd.read_csv(C.SENSOR_FILES[batch])
    tz, unit = props[batch]["timezone"], props[batch]["unit_type"]
    local, date = to_local_date(raw["timestamp"], tz)
    df = pd.DataFrame({"sensor_id": raw["sensor_id"].str.strip(), "date": date,
                       "raw_value": raw["reading_value"].astype(float)})

    # Step 4: sentinel -> NaN BEFORE any calculation.
    sentinel = df["raw_value"] == C.SENTINEL
    impossible = (df["raw_value"] < 0) & ~sentinel
    df["value"] = df["raw_value"].mask(sentinel | impossible)

    # Step 3: unit conversion to PM2.5 (ug/m3).
    if unit.upper() == "AQI":
        df["pm25"] = aqi_to_pm25(df["value"])
    elif unit.upper() in ("PM2.5", "PM25"):
        df["pm25"] = df["value"]
    else:
        raise ValueError(f"Unknown unit in metadata: {unit}")

    # Step 5: flatline detection on the native readings, per sensor.
    df = df.sort_values(["sensor_id", "date"]).reset_index(drop=True)
    df["flatline"] = False
    for sid, idx in df.groupby("sensor_id").groups.items():
        df.loc[idx, "flatline"] = flatline_mask(df.loc[idx, "value"].to_numpy())
    df.loc[df["flatline"], "pm25"] = np.nan

    hours = sorted(local.dt.hour.unique().tolist())
    audit["networks"][batch] = {
        "file": C.SENSOR_FILES[batch].name, "timezone": tz, "unit": unit,
        "rows": int(len(df)), "sensors": int(df["sensor_id"].nunique()),
        "local_date_range": [str(df["date"].min().date()), str(df["date"].max().date())],
        "local_hours_after_alignment": hours,
        "sentinel_minus_999": int(sentinel.sum()),
        "negative_values": int(impossible.sum()),
        "duplicate_sensor_days": int(df.duplicated(["sensor_id", "date"]).sum()),
    }
    runs = []
    for sid, g in df[df["flatline"]].groupby("sensor_id"):
        g = g.sort_values("date")
        block = (g["date"].diff() != pd.Timedelta(days=1)).cumsum()
        for _, b in g.groupby(block):
            runs.append({"sensor_id": sid, "start": str(b["date"].min().date()),
                         "end": str(b["date"].max().date()), "days": int(len(b)),
                         "stuck_value": float(b["value"].iloc[0])})
    audit["networks"][batch]["flatline_runs"] = runs
    return df[["sensor_id", "date", "pm25", "flatline", "raw_value"]]


def build_daily(save=True):
    """Return the clean daily PM2.5 table (one row per sensor per PKT date)."""
    meta = load_metadata()
    props = batch_properties(meta)
    audit = {"batch_properties": props, "networks": {}}

    nets = {b: load_network(b, props, audit) for b in sorted(C.SENSOR_FILES)}
    a = nets["batch_1"].rename(columns={"pm25": "pm25_b1", "flatline": "flat_b1", "raw_value": "raw_b1"})
    b = nets["batch_2"].rename(columns={"pm25": "pm25_b2", "flatline": "flat_b2", "raw_value": "raw_b2"})
    daily = a.merge(b, on=["sensor_id", "date"], how="outer")

    # Cross-network agreement check (same area, same day, after conversion).
    both = daily[["pm25_b1", "pm25_b2"]].dropna()
    diff = (both["pm25_b1"] - both["pm25_b2"]).abs()
    aqi_from_b1 = pm25_to_aqi(daily["raw_b1"].where(daily["raw_b1"] != C.SENTINEL))
    valid_aqi = (daily["raw_b2"] != C.SENTINEL) & ~np.isnan(aqi_from_b1)
    exact = (aqi_from_b1[valid_aqi] == daily.loc[valid_aqi, "raw_b2"]).mean()
    audit["cross_network"] = {
        "sensor_days_with_both_valid": int(len(both)),
        "mean_abs_diff_ug": round(float(diff.mean()), 3),
        "max_abs_diff_ug": round(float(diff.max()), 3),
        "aqi_exact_match_rate": round(float(exact), 4),
        "note": "batch_2 AQI equals the EPA AQI of batch_1 PM2.5 once batch_1 is "
                "shifted from UTC to PKT; without the shift the days misalign by one.",
    }

    # Step 6: daily average of the valid converted readings (both networks).
    daily["n_valid"] = daily[["pm25_b1", "pm25_b2"]].notna().sum(axis=1)
    daily["pm25"] = daily[["pm25_b1", "pm25_b2"]].mean(axis=1)

    # Step 7: interpolate remaining gaps in time, per sensor (never drop rows).
    daily = daily.sort_values(["sensor_id", "date"]).reset_index(drop=True)
    daily["imputed"] = daily["pm25"].isna()
    daily["pm25"] = daily.groupby("sensor_id")["pm25"].transform(
        lambda s: s.interpolate(method="linear", limit_direction="both"))
    daily = daily.merge(meta[["sensor_id", "area", "batch"]], on="sensor_id", how="left")

    confirmed = []
    for r1 in audit["networks"]["batch_1"]["flatline_runs"]:
        for r2 in audit["networks"]["batch_2"]["flatline_runs"]:
            if r1["sensor_id"] == r2["sensor_id"] and r1["start"] <= r2["end"] and r2["start"] <= r1["end"]:
                confirmed.append({**r1, "aqi_network_stuck_value": r2["stuck_value"]})
    audit["flatline_confirmed_both_networks"] = confirmed
    audit["flatline_note"] = (
        "Runs of 3+ identical readings are dropped in each network. In the AQI network "
        "short runs also occur from integer rounding (1 AQI step is about 1.9 ug/m3 in the "
        "151-200 band); for those days the PM2.5 network still varies, so its reading is "
        "kept. Only a run seen in BOTH networks is a confirmed hardware fault.")
    audit["sentinel_filled_from_other_network"] = int(
        ((daily["raw_b1"] == C.SENTINEL) | (daily["raw_b2"] == C.SENTINEL)).sum()
        - (daily["imputed"] & ((daily["raw_b1"] == C.SENTINEL) | (daily["raw_b2"] == C.SENTINEL))).sum())
    audit["interpolated_sensor_days"] = [
        {"sensor_id": r.sensor_id, "date": str(r.date.date())}
        for r in daily[daily["imputed"]].itertuples()]
    audit["final"] = {
        "rows": int(len(daily)), "sensors": int(daily["sensor_id"].nunique()),
        "date_range": [str(daily["date"].min().date()), str(daily["date"].max().date())],
        "missing_after_cleaning": int(daily["pm25"].isna().sum()),
        "hazardous_sensor_days": int((daily.loc[~daily["imputed"], "pm25"] >= C.HAZARD_THRESHOLD).sum()),
    }

    out = daily[["sensor_id", "area", "date", "pm25", "pm25_b1", "pm25_b2", "n_valid", "imputed"]]
    if save:
        C.ARTIFACTS_DIR.mkdir(exist_ok=True)
        out.assign(date=out["date"].dt.strftime("%Y-%m-%d")).to_csv(C.DAILY_CLEAN_CSV, index=False)
        C.AUDIT_JSON.write_text(json.dumps(audit, indent=2))
    return out, audit


def load_weather():
    """Historical + holdout weather in one frame indexed by date (no gaps allowed)."""
    hist = pd.read_csv(C.WEATHER_HISTORY, parse_dates=["date"])
    hold = pd.read_csv(C.HOLDOUT_WEATHER, parse_dates=["date"])
    w = pd.concat([hist, hold]).drop_duplicates("date").sort_values("date").set_index("date")
    w = w.mask(w == C.SENTINEL)
    full = pd.date_range(w.index.min(), w.index.max(), freq="D")
    assert len(full) == len(w), "weather has missing dates"
    return w.interpolate(limit_direction="both")


if __name__ == "__main__":
    d, a = build_daily()
    print(json.dumps(a, indent=2)[:3000])
