"""Validate predictions.csv against SPEC.md section 4. Exit code 0 = pass.

Usage:  python validate_submission.py [path/to/predictions.csv]
"""
import math
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent


def alarm_threshold():
    """The official SPEC section 3 rule: hazardous when predicted PM2.5 >= 165."""
    return 165.0


def validate(path):
    errors = []
    path = Path(path)
    if path.name != "predictions.csv":
        errors.append(f"filename must be exactly predictions.csv (got {path.name})")
    if not path.exists():
        return [f"{path} not found - run: python run_pipeline.py"]

    template_cols = list(pd.read_csv(ROOT / "templates" / "predictions_template.csv", nrows=0).columns)
    raw_header = path.read_text().splitlines()[0].split(",")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    holdout = pd.read_csv(ROOT / "holdout" / "holdout_inputs.csv", dtype=str)

    if raw_header != template_cols:
        errors.append(f"columns {raw_header} != template {template_cols}")
    if any(c.startswith("Unnamed") or c == "" for c in raw_header):
        errors.append("unnamed index column present")
    if len(df) != 150:
        errors.append(f"expected 150 rows, found {len(df)}")
    if (df == "").any().any():
        errors.append("missing cells found")
    if df.duplicated().any() or df.duplicated(["sensor_id", "target_date"]).any():
        errors.append("duplicate rows or duplicate (sensor_id, target_date) pairs")

    want = set(zip(holdout["sensor_id"], holdout["target_date"]))
    got = set(zip(df.get("sensor_id", []), df.get("target_date", [])))
    if want != got:
        errors.append(f"pairs differ from holdout_inputs.csv: missing={len(want - got)} extra={len(got - want)}")

    for d in df.get("target_date", []):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            errors.append(f"bad date format: {d}")
            break
    for v in df.get("predicted_pm25", []):
        try:
            x = float(v)
            if not math.isfinite(x) or x == -999 or x < 0:
                raise ValueError
        except ValueError:
            errors.append(f"predicted_pm25 must be a finite non-negative float, got {v!r}")
            break
    if not set(df.get("hazardous", [])) <= {"0", "1"}:
        errors.append(f"hazardous must be 0 or 1, got {sorted(set(df['hazardous']))}")
    else:
        alarm_at = alarm_threshold()
        rule = (df["predicted_pm25"].astype(float) >= alarm_at).astype(int).astype(str)
        if not (rule == df["hazardous"]).all():
            errors.append(f"hazardous does not match the alarm rule (predicted_pm25 >= {alarm_at})")
    return errors


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else ROOT / "predictions.csv"
    problems = validate(target)
    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print(f"PASS: predictions.csv matches SPEC section 4 (150 rows, exact columns, hazardous = predicted PM2.5 >= {alarm_threshold():g})")
