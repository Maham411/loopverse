"""One command to regenerate every Sprint 1 output from the supplied inputs.

    python run_pipeline.py

Writes predictions.csv, artifacts/daily_pm25_clean.csv, artifacts/data_audit.json
and artifacts/model_report.json, then validates predictions.csv against SPEC.
"""
import sys
import time

from smogguard import config as C
from smogguard.model import run
from validate_submission import validate

if __name__ == "__main__":
    t0 = time.time()
    preds, report, audit = run(write=True)
    problems = validate(C.PREDICTIONS_CSV)
    t = report["test_october"]["ridge_one_step"]
    print(f"Cleaned data: {audit['final']['rows']} sensor-days, {audit['final']['missing_after_cleaning']} missing, "
          f"flatline fixed: {[r['sensor_id'] for r in audit['flatline_confirmed_both_networks']]}")
    print(f"Model: {report['chosen']['model']} ({report['chosen']['features']}, alpha={report['chosen']['alpha']})")
    print(f"October test: MAE {t['mae']:.2f} | hazardous caught {t['hazardous_caught']}/{t['hazardous_days']} | "
          f"false alarms {t['false_alarms']} | baseline 7-day mean MAE {report['baselines_october']['rolling_mean_7d']['mae']:.2f}")
    al = report["alarm"]
    ta = al["test_october_recursive"]
    print(f"Advisory watch level (dashboard/assistant only): {al['threshold']:g} ug/m3 | October check: caught "
          f"{ta['hazardous_caught']}/{ta['hazardous_days']} hazardous days, {ta['false_alarms']} false alarms "
          f"(the plain 165 rule caught {al['test_october_recursive_at_165']['hazardous_caught']})")
    print(f"predictions.csv: {len(preds)} rows, {int(preds['hazardous'].sum())} hazardous (official >= 165 rule), "
          f"range {preds['predicted_pm25'].min():.1f}-{preds['predicted_pm25'].max():.1f} ug/m3")
    print("SPEC check:", "PASS" if not problems else "FAIL " + "; ".join(problems))
    print(f"Done in {time.time() - t0:.1f}s")
    sys.exit(1 if problems else 0)
