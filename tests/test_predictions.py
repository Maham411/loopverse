"""predictions.csv submission gate (SPEC section 4)."""
import pandas as pd

from smogguard import config as C
from validate_submission import validate


def test_predictions_pass_spec_validator():
    assert validate(C.PREDICTIONS_CSV) == []


def test_exact_shape_and_rule():
    df = pd.read_csv(C.PREDICTIONS_CSV)
    assert list(df.columns) == ["sensor_id", "target_date", "predicted_pm25", "hazardous"]
    assert len(df) == 150 and df["sensor_id"].nunique() == 15 and df["target_date"].nunique() == 10
    from validate_submission import alarm_threshold
    t = alarm_threshold()
    assert 115 <= t <= 165
    assert ((df["predicted_pm25"] >= t).astype(int) == df["hazardous"]).all()


def test_validator_rejects_bad_files(tmp_path):
    good = pd.read_csv(C.PREDICTIONS_CSV)
    bad = tmp_path / "predictions.csv"
    good.head(149).to_csv(bad, index=False)
    assert any("150" in e for e in validate(bad))
    good.to_csv(bad)  # pandas index column -> must fail
    assert validate(bad)
    g2 = good.copy()
    g2.loc[0, "predicted_pm25"] = -999
    g2.to_csv(bad, index=False)
    assert validate(bad)
