"""SmogGuard AI local web server.

Run:  python -m uvicorn app.server:app --port 8000   then open http://localhost:8000
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from smogguard import config as C  # noqa: E402
from smogguard.assistant import ask_detailed  # noqa: E402
from smogguard.data_pipeline import pm25_to_aqi  # noqa: E402
from smogguard.documents import get_store  # noqa: E402
from smogguard.forecast_tool import forecast  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
app = FastAPI(title="SmogGuard AI", version="1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# Approximate positions for a schematic map only (not survey-grade coordinates).
APPROX_COORDS = {
    "Gulberg": (31.517, 74.348), "DHA": (31.474, 74.408), "Johar Town": (31.469, 74.272),
    "Model Town": (31.483, 74.326), "Wagah": (31.605, 74.573), "Thokar Niaz Baig": (31.472, 74.240),
    "Allama Iqbal Town": (31.510, 74.290), "Shadman": (31.540, 74.330), "Cantt": (31.515, 74.390),
    "Faisal Town": (31.478, 74.305), "Township": (31.447, 74.310), "Walled City": (31.582, 74.315),
    "Raiwind Road": (31.420, 74.265), "Bahria Town": (31.367, 74.185), "Airport Road": (31.505, 74.405),
}


class AskBody(BaseModel):
    question: str
    question_id: str | None = None


def _band(pm):
    return "hazardous" if pm >= C.HAZARD_THRESHOLD else ("unhealthy" if pm >= 100 else "low")


@lru_cache(maxsize=1)
def build_overview():
    daily = pd.read_csv(C.DAILY_CLEAN_CSV)
    preds = pd.read_csv(C.PREDICTIONS_CSV, dtype={"target_date": str})
    meta = pd.read_csv(C.SENSOR_METADATA, dtype=str)
    audit = json.loads(C.AUDIT_JSON.read_text())
    report = json.loads(C.MODEL_REPORT_JSON.read_text())
    store = get_store()

    last_day = daily["date"].max()
    today = daily[daily["date"] == last_day]
    next_day = preds["target_date"].min()
    nxt = preds[preds["target_date"] == next_day]
    city_now = float(today["pm25"].mean())
    city_next = float(nxt["predicted_pm25"].mean())
    worst_next = nxt.loc[nxt["predicted_pm25"].idxmax()]

    areas = []
    for r in meta.itertuples():
        hist = daily[daily["sensor_id"] == r.sensor_id].sort_values("date").tail(21)
        fc = preds[preds["sensor_id"] == r.sensor_id].sort_values("target_date")
        lat, lon = APPROX_COORDS.get(r.area, (None, None))
        areas.append({
            "sensor_id": r.sensor_id, "area": r.area, "native_network": r.batch,
            "lat": lat, "lon": lon,
            "last_observed": round(float(hist["pm25"].iloc[-1]), 1),
            "history": [{"date": d, "pm25": round(float(v), 1)} for d, v in zip(hist["date"], hist["pm25"])],
            "forecasts": [{"date": d, "pm25": round(float(v), 1), "hazardous": bool(h)}
                          for d, v, h in zip(fc["target_date"], fc["predicted_pm25"], fc["hazardous"])],
        })

    city_hist = daily.groupby("date")["pm25"].mean().tail(45)
    city_fc = preds.groupby("target_date")["predicted_pm25"].mean()

    # Health advice summary for the worst area tomorrow, straight from DOC-01's matching band.
    band = _band(float(worst_next["predicted_pm25"]))
    advice = [c.text for c in store.docs["DOC-01"].chunks
              if (band == "hazardous" and "hazardous range" in c.lead_in)
              or (band == "unhealthy" and "100–164" in c.lead_in)
              or (band == "low" and "below 100" in c.lead_in)]
    pollutant = next((c.text for c in store.docs["DOC-04"].chunks if c.text.startswith("What is PM2.5?")), "")

    n1, n2 = audit["networks"]["batch_1"], audit["networks"]["batch_2"]
    return {
        "title": "SmogGuard AI — Predict. Explain. Protect.",
        "last_observed_date": last_day, "next_forecast_date": next_day,
        "forecast_dates": sorted(preds["target_date"].unique().tolist()),
        "hazard_threshold": C.HAZARD_THRESHOLD,
        "metrics": {
            "current_avg_pm25": round(city_now, 1),
            "current_avg_aqi": int(pm25_to_aqi([city_now])[0]),
            "next_avg_pm25": round(city_next, 1),
            "next_avg_aqi": int(pm25_to_aqi([city_next])[0]),
            "next_max": {"area": meta.set_index("sensor_id").loc[worst_next["sensor_id"], "area"],
                         "pm25": round(float(worst_next["predicted_pm25"]), 1)},
            "next_hazardous_areas": int((nxt["predicted_pm25"] >= C.HAZARD_THRESHOLD).sum()),
            "next_alert_areas": int(((nxt["predicted_pm25"] >= report.get("alarm", {}).get("threshold", C.HAZARD_THRESHOLD))
                                     & (nxt["predicted_pm25"] < C.HAZARD_THRESHOLD)).sum()),
            "alert_level": report.get("alarm", {}).get("threshold", C.HAZARD_THRESHOLD),
            "main_pollutant": "PM2.5", "main_pollutant_source": "DOC-04",
            "main_pollutant_note": pollutant.split("? ", 1)[-1],
            "advice_band": band, "advice": advice, "advice_source": "DOC-01",
        },
        "areas": areas,
        "city_trend": {"observed": [{"date": d, "pm25": round(float(v), 1)} for d, v in city_hist.items()],
                       "forecast": [{"date": d, "pm25": round(float(v), 1)} for d, v in city_fc.items()]},
        "data_quality": {
            "networks": [
                {"name": "Batch 1", "file": n1["file"], "timezone": n1["timezone"], "unit": n1["unit"],
                 "sentinels": n1["sentinel_minus_999"], "flatline_runs": n1["flatline_runs"]},
                {"name": "Batch 2", "file": n2["file"], "timezone": n2["timezone"], "unit": n2["unit"],
                 "sentinels": n2["sentinel_minus_999"], "flatline_runs": n2["flatline_runs"]},
            ],
            "timezone_note": ("Batch 1 timestamps are 19:00 UTC, which is 00:00 Pakistan time on the next "
                              "day. Converted with tz Asia/Karachi (+5 h) before merging."),
            "conversion": audit["cross_network"],
            "flatline_confirmed": audit["flatline_confirmed_both_networks"],
            "flatline_note": audit["flatline_note"],
            "filled_from_other_network": audit["sentinel_filled_from_other_network"],
            "interpolated": audit["interpolated_sensor_days"],
            "final": audit["final"],
        },
        "model": {
            "chosen": report["chosen"], "split": report["split"],
            "test": report["test_october"], "baselines": report["baselines_october"],
            "weights": report["weights_final"], "sweep": report["alarm_threshold_sweep_october"],
            "alarm": report.get("alarm", {}),
            "holdout": report["holdout"],
        },
        "documents": store.audit(),
    }


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    from smogguard import llm
    return {"status": "ok", "predictions": C.PREDICTIONS_CSV.exists(), "llm": llm.backend()}


@app.get("/api/overview")
def overview():
    return build_overview()


@app.post("/api/ask")
def api_ask(body: AskBody):
    response, details = ask_detailed(body.question, body.question_id)
    return {"response": response, "details": details}


@app.get("/api/forecast")
def api_forecast(location: str, date: str):
    return forecast(location, date)
