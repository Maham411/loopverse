import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from smogguard import config as C  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def pipeline_outputs():
    """Make sure predictions.csv and the reports exist (regenerate if missing)."""
    if not (C.PREDICTIONS_CSV.exists() and C.MODEL_REPORT_JSON.exists() and C.AUDIT_JSON.exists()):
        from smogguard.model import run
        run(write=True)
    from smogguard import forecast_tool
    forecast_tool.reload()
    yield


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Tests use the deterministic composer unless a test plugs in a fake LLM."""
    from smogguard import llm
    monkeypatch.setenv("SMOGGUARD_LLM", "off")
    monkeypatch.delenv("SMOGGUARD_TODAY", raising=False)
    llm.GENERATOR = None
    yield
    llm.GENERATOR = None
