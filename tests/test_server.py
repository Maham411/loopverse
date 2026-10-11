"""Web API smoke tests (FastAPI TestClient, no browser needed)."""
from fastapi.testclient import TestClient

from app.server import app

client = TestClient(app)


def test_pages_and_health():
    assert client.get("/").status_code == 200 and "SmogGuard AI" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["predictions"] is True and h["llm"] in ("off", "groq", "ollama")


def test_overview_contents():
    d = client.get("/api/overview").json()
    assert len(d["areas"]) == 15 and len(d["forecast_dates"]) == 10
    assert all(len(a["forecasts"]) == 10 for a in d["areas"])
    assert d["metrics"]["main_pollutant"] == "PM2.5" and d["metrics"]["advice"]
    assert d["data_quality"]["flatline_confirmed"][0]["sensor_id"] == "S07"
    status = {doc["doc_id"]: doc for doc in d["documents"]}
    assert status["DOC-02"]["status"] == "superseded" and status["DOC-07"]["hidden_content_removed"]


def test_ask_endpoint_schema():
    r = client.post("/api/ask", json={"question": "Will schools in Gulberg close tomorrow?", "question_id": "Q1"}).json()
    assert list(r["response"]) == ["question_id", "answer", "sources", "forecast_called"]
    assert r["response"]["question_id"] == "Q1" and r["response"]["forecast_called"] is True
    assert r["details"]["forecasts"][0]["location"] == "Gulberg"


def test_forecast_endpoint():
    assert client.get("/api/forecast", params={"location": "DHA", "date": "2026-11-01"}).json()["status"] == "ok"
    bad = client.get("/api/forecast", params={"location": "Quetta", "date": "2026-11-01"}).json()
    assert bad["status"] == "unavailable" and bad["pm25"] is None
