"""Sprint 1 forecasting: next-day PM2.5 per sensor with a Ridge regression.

Leakage rules enforced here:
  * Every feature for target date T is built from data up to T-1 only
    (pandas .shift(1) before any rolling window).
  * Model selection uses backtests that end on/before TRAIN_END (September);
    October is used once as the test period; nothing is shuffled.
  * The StandardScaler lives inside the sklearn Pipeline, so it is fitted on
    the training rows only.
  * Holdout origins after the last observed day (2026-10-28) have no sensor
    readings, so those days are filled recursively with our OWN earlier
    forecasts - never with any information from the future.
"""
import json

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import config as C
from .data_pipeline import build_daily, load_weather

LAG_FEATURES = ["lag1", "roll3", "roll7", "roll14", "roll28"]
WEATHER = ["temp_c", "humidity_pct", "wind_kmh"]
FEATURE_SETS = {
    "lags": LAG_FEATURES,
    "lags+weather_lag1": LAG_FEATURES + [f"{w}_lag1" for w in WEATHER],
    "lags+weather_target_day": LAG_FEATURES + [f"{w}_target" for w in WEATHER],
}
ALPHAS = [0.1, 1.0, 10.0, 100.0]
HORIZON = 10


# ---------------------------------------------------------------- features
def make_features(pm_wide, weather, target_dates):
    """Feature rows for each (sensor, target_date). pm_wide: index=date, cols=sensor."""
    past = pm_wide.shift(1)  # value known at the forecast origin (T-1)
    feats = {
        "lag1": past,
        "roll3": past.rolling(3).mean(),
        "roll7": past.rolling(7).mean(),
        "roll14": past.rolling(14).mean(),
        "roll28": past.rolling(28).mean(),
    }
    target_dates = pd.DatetimeIndex(target_dates)
    rows = []
    for sid in pm_wide.columns:
        f = pd.DataFrame({k: v[sid] for k, v in feats.items()}).reindex(target_dates)
        f["sensor_id"] = sid
        rows.append(f)
    X = pd.concat(rows).rename_axis("target_date").reset_index()
    w_lag = weather.shift(1).add_suffix("_lag1")      # weather at the origin day
    w_tgt = weather.add_suffix("_target")             # weather forecast for T (SPEC allows)
    X = X.join(w_lag, on="target_date").join(w_tgt, on="target_date")
    return X


def training_frame(daily, weather, last_target):
    """Features + target for every target date <= last_target (imputed targets dropped)."""
    pm = daily.pivot(index="date", columns="sensor_id", values="pm25")
    imp = daily.pivot(index="date", columns="sensor_id", values="imputed")
    pm = pm.loc[:last_target]
    X = make_features(pm, weather, pm.index)
    long_pm = pm.stack().rename("y")
    long_imp = imp.loc[:last_target].stack().rename("imputed")
    X = X.join(long_pm, on=["target_date", "sensor_id"]).join(long_imp, on=["target_date", "sensor_id"])
    X = X[~X["imputed"].astype(bool)]
    return X.dropna(subset=LAG_FEATURES + ["y"]).reset_index(drop=True)


def fit_ridge(X, features, alpha):
    model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    return model.fit(X[features], X["y"])


def recursive_forecast(model, features, pm_wide, weather, start, end):
    """Forecast every day start..end. Unobserved days are filled with predictions."""
    pm = pm_wide.loc[: pd.Timestamp(start) - pd.Timedelta(days=1)].copy()
    out = {}
    for day in pd.date_range(start, end, freq="D"):
        pm.loc[day] = np.nan
        X = make_features(pm, weather, [day])
        pred = model.predict(X[features])
        pm.loc[day, X["sensor_id"].to_numpy()] = pred
        out[day] = pd.Series(pred, index=X["sensor_id"].to_numpy())
    return pd.DataFrame(out).T


# ---------------------------------------------------------------- metrics
def metrics(pred, actual, alarm_at=C.HAZARD_THRESHOLD):
    """Error + alarm quality. A day IS hazardous if actual >= 165; we ALARM if pred >= alarm_at."""
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    hz, alarm = actual >= C.HAZARD_THRESHOLD, pred >= alarm_at
    tp, fp, fn = int((alarm & hz).sum()), int((alarm & ~hz).sum()), int((~alarm & hz).sum())
    return {
        "n": int(len(actual)),
        "mae": round(float(np.abs(pred - actual).mean()), 3),
        "rmse": round(float(np.sqrt(((pred - actual) ** 2).mean())), 3),
        "bias": round(float((pred - actual).mean()), 3),
        "hazardous_days": int(hz.sum()),
        "hazardous_recall": round(tp / hz.sum(), 3) if hz.sum() else None,
        "hazardous_caught": tp,
        "false_alarms": fp,
        "missed_hazardous": fn,
        "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
        "accuracy": round(float((alarm == hz).mean()), 3),
    }


def backtest_preds(daily, weather, features, alpha, cutoffs):
    """Recursive HORIZON-day backtests -> (predictions, actuals) arrays."""
    pm = daily.pivot(index="date", columns="sensor_id", values="pm25")
    imp = daily.pivot(index="date", columns="sensor_id", values="imputed")
    preds, acts = [], []
    for cut in cutoffs:
        cut = pd.Timestamp(cut)
        model = fit_ridge(training_frame(daily, weather, cut), features, alpha)
        start, end = cut + pd.Timedelta(days=1), cut + pd.Timedelta(days=HORIZON)
        p = recursive_forecast(model, features, pm, weather, start, end)
        keep = ~imp.loc[start:end].astype(bool)
        preds.append(p.where(keep).stack())
        acts.append(pm.loc[start:end].where(keep).stack())
    p, a = pd.concat(preds), pd.concat(acts)
    return p.to_numpy(), a.reindex(p.index).to_numpy()


def choose_alarm(pred, actual):
    """Alarm level with the best F1 (balances caught hazardous days vs false alarms).
    Ties go to the higher level (fewer false alarms)."""
    table, best = [], None
    for t in C.ALARM_GRID:
        m = metrics(pred, actual, alarm_at=t)
        tp, fp, fn = m["hazardous_caught"], m["false_alarms"], m["missed_hazardous"]
        f1 = round(2 * tp / (2 * tp + fp + fn), 4) if tp else 0.0
        table.append({"alarm_at": t, "caught": tp, "hazardous_days": m["hazardous_days"],
                      "false_alarms": fp, "f1": f1})
        if best is None or f1 > best[1]:
            best = (t, f1)
    return best[0], table


def backtest(daily, weather, features, alpha, cutoffs):
    """Recursive HORIZON-day backtests. Train on targets <= cutoff each time."""
    pm = daily.pivot(index="date", columns="sensor_id", values="pm25")
    imp = daily.pivot(index="date", columns="sensor_id", values="imputed")
    preds, acts = [], []
    for cut in cutoffs:
        cut = pd.Timestamp(cut)
        model = fit_ridge(training_frame(daily, weather, cut), features, alpha)
        start, end = cut + pd.Timedelta(days=1), cut + pd.Timedelta(days=HORIZON)
        p = recursive_forecast(model, features, pm, weather, start, end)
        keep = ~imp.loc[start:end].astype(bool)
        preds.append(p.where(keep).stack())
        acts.append(pm.loc[start:end].where(keep).stack())
    p, a = pd.concat(preds), pd.concat(acts)
    return metrics(p.to_numpy(), a.reindex(p.index).to_numpy())


def effective_weights(model, features):
    """Ridge coefficients converted back to raw units (ug/m3 per ug/m3)."""
    scaler, ridge = model.named_steps["standardscaler"], model.named_steps["ridge"]
    coef = ridge.coef_ / scaler.scale_
    intercept = ridge.intercept_ - float(np.sum(ridge.coef_ * scaler.mean_ / scaler.scale_))
    return {"intercept": round(float(intercept), 3),
            **{f: round(float(c), 4) for f, c in zip(features, coef)}}


# ---------------------------------------------------------------- main run
def run(write=True):
    daily, audit = build_daily(save=write)
    weather = load_weather()
    report = {"split": {}, "selection": [], "test_october": {}, "baselines_october": {}}

    # 1) Chronological split
    train_end = pd.Timestamp(C.TRAIN_END)
    last_obs = daily["date"].max()
    train = training_frame(daily, weather, train_end)
    full = training_frame(daily, weather, last_obs)
    test = full[full["target_date"] > train_end]
    report["split"] = {
        "train_targets": [str(train["target_date"].min().date()), str(train["target_date"].max().date())],
        "test_targets": [str(test["target_date"].min().date()), str(test["target_date"].max().date())],
        "train_rows": int(len(train)), "test_rows": int(len(test)),
        "shuffled": False,
    }
    assert train["target_date"].max() < test["target_date"].min(), "train/test overlap"

    # 2) Model selection with recursive backtests that stay inside the training period
    sel_cutoffs = ["2026-09-01", "2026-09-10", "2026-09-20"]
    best = None
    for name, feats in FEATURE_SETS.items():
        for alpha in ALPHAS:
            m = backtest(daily, weather, feats, alpha, sel_cutoffs)
            report["selection"].append({"features": name, "alpha": alpha, **m})
            if best is None or m["mae"] < best[2]:
                best = (name, alpha, m["mae"])
    best_name, best_alpha, _ = best
    features = FEATURE_SETS[best_name]
    report["chosen"] = {"model": "Ridge regression (L2)", "features": best_name,
                        "feature_list": features, "alpha": best_alpha,
                        "selected_on": f"recursive {HORIZON}-day backtests at cutoffs {sel_cutoffs}"}

    # 3) Single October test: train <= Sep 30, one-step-ahead on Oct 1..28
    model = fit_ridge(train, features, best_alpha)
    y = test["y"].to_numpy()
    report["test_october"]["ridge_one_step"] = metrics(model.predict(test[features]), y)
    report["test_october"]["ridge_recursive_10day"] = backtest(
        daily, weather, features, best_alpha, ["2026-10-08", "2026-10-18"])
    report["baselines_october"] = {
        "persistence_lag1": metrics(test["lag1"], y),
        "rolling_mean_7d": metrics(test["roll7"], y),
        "rolling_mean_14d": metrics(test["roll14"], y),
        "always_not_hazardous": metrics(np.zeros_like(y), y),
    }
    lin = make_pipeline(StandardScaler(), LinearRegression()).fit(train[features], train["y"])
    report["baselines_october"]["linear_regression_same_features"] = metrics(lin.predict(test[features]), y)
    allf = FEATURE_SETS["lags+weather_target_day"] + [f"{w}_lag1" for w in WEATHER]
    hgb = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, random_state=C.RANDOM_SEED)
    hgb.fit(train[allf], train["y"])
    report["baselines_october"]["gradient_boosting_all_features"] = metrics(hgb.predict(test[allf]), y)

    # Alarm threshold sweep (analysis only - predictions.csv follows SPEC: >= 165)
    p_test = model.predict(test[features])
    truly_hazardous = y >= C.HAZARD_THRESHOLD
    sweep = []
    for t in (165, 150, 140, 130, 120):
        alarm = p_test >= t
        sweep.append({"alarm_if_pred_at_or_above": t,
                      "hazardous_days": int(truly_hazardous.sum()),
                      "hazardous_caught": int((alarm & truly_hazardous).sum()),
                      "false_alarms": int((alarm & ~truly_hazardous).sum())})
    report["alarm_threshold_sweep_october"] = sweep

    # Calibrated hazardous ALERT (Trap 4). Chosen on September multi-day backtests
    # (the same chained forecasting used for the holdout), then checked once on October.
    sel_p, sel_a = backtest_preds(daily, weather, features, best_alpha, sel_cutoffs)
    alarm_at, sel_table = choose_alarm(sel_p, sel_a)
    oct_p, oct_a = backtest_preds(daily, weather, features, best_alpha, ["2026-10-08", "2026-10-18"])
    report["alarm"] = {
        "threshold": alarm_at,
        "definition": ("Advisory early-warning WATCH level, shown in the dashboard and assistant only. "
                       "predictions.csv keeps the official SPEC rule: hazardous = predicted PM2.5 >= 165."),
        "applied_to_predictions_csv": False,
        "why": ("Hazardous days are sudden spikes that no model here can predict, so the official 165 rule "
                "on a smooth forecast flags nothing (like the 'always not hazardous' model). The alert level "
                "is calibrated on recall and false alarms, as the handbook recommends."),
        "chosen_on": f"F1 on recursive {HORIZON}-day backtests at {sel_cutoffs}",
        "selection_table": sel_table,
        "test_october_recursive": metrics(oct_p, oct_a, alarm_at=alarm_at),
        "test_october_recursive_at_165": metrics(oct_p, oct_a),
    }
    report["weights_trained_to_sep30"] = effective_weights(model, features)

    # 4) Final model: refit on ALL observed targets, forecast the holdout window
    final = fit_ridge(full, features, best_alpha)
    report["weights_final"] = effective_weights(final, features)
    report["final_training_rows"] = int(len(full))
    holdout = pd.read_csv(C.HOLDOUT_INPUTS, dtype=str)
    holdout["target_dt"] = pd.to_datetime(holdout["target_date"])
    holdout["origin_dt"] = pd.to_datetime(holdout["forecast_origin_date"])
    assert (holdout["target_dt"] - holdout["origin_dt"] == pd.Timedelta(days=1)).all()
    assert holdout["target_dt"].min() > last_obs, "holdout target overlaps observed data"
    pm = daily.pivot(index="date", columns="sensor_id", values="pm25")
    fc = recursive_forecast(final, features, pm, weather,
                            last_obs + pd.Timedelta(days=1), holdout["target_dt"].max())
    holdout["predicted_pm25"] = [round(float(np.clip(fc.loc[t, s], C.MIN_PM25, None)), 2)
                                 for t, s in zip(holdout["target_dt"], holdout["sensor_id"])]
    assert np.isfinite(holdout["predicted_pm25"]).all() and (holdout["predicted_pm25"] >= C.MIN_PM25).all()
    # SPEC section 3: hazardous = predicted PM2.5 >= 165. The calibrated level is advisory only.
    holdout["hazardous"] = (holdout["predicted_pm25"] >= C.HAZARD_THRESHOLD).astype(int)
    report["holdout"] = {
        "last_observed_date": str(last_obs.date()),
        "origins_with_observed_data": int((holdout["origin_dt"] <= last_obs).sum()),
        "origins_filled_with_own_forecasts": int((holdout["origin_dt"] > last_obs).sum()),
        "predicted_range": [float(holdout["predicted_pm25"].min()), float(holdout["predicted_pm25"].max())],
        "hazardous_predictions": int(holdout["hazardous"].sum()),
        "rule_in_predictions_csv": "predicted_pm25 >= 165 (SPEC section 3)",
        "watch_level_advisory": alarm_at,
        "on_watch_advisory": int((holdout["predicted_pm25"] >= alarm_at).sum()),
    }

    cols = list(pd.read_csv(C.PREDICTIONS_TEMPLATE, nrows=0).columns)
    preds = holdout[cols]
    if write:
        preds.to_csv(C.PREDICTIONS_CSV, index=False)
        C.MODEL_REPORT_JSON.write_text(json.dumps(report, indent=2))
    return preds, report, audit


if __name__ == "__main__":
    p, r, _ = run()
    print(json.dumps({k: r[k] for k in ("split", "chosen", "test_october", "holdout")}, indent=2))
