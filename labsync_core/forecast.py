"""Baseline demand forecasting with an honest rolling-origin backtest (docs/02, docs/09 F).

Methods: weighted 3-week moving average (the default fallback), EWMA and naive
("next week equals last week"). Each is backtested by fitting on weeks 1..k-1 and
predicting week k for k = 4..n, never seeing the week it predicts. The method
with the lowest MAE wins; ties go to the moving average. The low/high band is the
point forecast +/- the largest backtest error: an illustrative range, not a
calibrated interval. This is a rules baseline, not ML.
"""
from . import policy
from .values import as_num

METHOD_ORDER = ["weighted_moving_average", "ewma", "naive"]


def moving_average_forecast(series, window=3, weighted=True):
    """Next value from the last `window` points; recent weeks weigh more when `weighted` (1,2,3...)."""
    if not series:
        raise ValueError("empty series")
    recent = [float(x) for x in series[-window:]]
    weights = list(range(1, len(recent) + 1)) if weighted else [1] * len(recent)
    return sum(w * x for w, x in zip(weights, recent)) / sum(weights)


def ewma_forecast(series, alpha=0.35):
    """EWMA_t = alpha * x_(t-1) + (1 - alpha) * EWMA_(t-1), seeded with the first value."""
    if not series:
        raise ValueError("empty series")
    level = float(series[0])
    for x in series[1:]:
        level = alpha * float(x) + (1 - alpha) * level
    return level


def naive_forecast(series):
    if not series:
        raise ValueError("empty series")
    return float(series[-1])


def _predictors(alpha):
    return {
        "weighted_moving_average": lambda s: moving_average_forecast(s, 3, True),
        "ewma": lambda s: ewma_forecast(s, alpha),
        "naive": naive_forecast,
    }


def backtest(series, predictor, first_test_week=4):
    """Rolling-origin backtest. Weeks are 1-indexed: train on 1..k-1, test on k, k = first..n.

    Returns {"predictions": [{"week_index", "train_size", "predicted", "actual", "abs_error"}], "mae"}.
    """
    rows = []
    for k in range(first_test_week, len(series) + 1):
        train = list(series[:k - 1])
        predicted = predictor(train)
        actual = float(series[k - 1])
        rows.append({"week_index": k, "train_size": len(train), "predicted": round(predicted, 4),
                     "actual": actual, "abs_error": round(abs(predicted - actual), 4)})
    mae = round(sum(r["abs_error"] for r in rows) / len(rows), 4) if rows else None
    return {"predictions": rows, "mae": mae}


def forecast_series(series, policies=None, known_booked_hours=None, capacity_hours=None):
    """Pick the best baseline by backtest MAE and forecast the next week.

    Args:
        series: weekly hours, oldest first (use requested hours: latent demand).
        known_booked_hours: hours already confirmed for the forecast week; the prediction is
            floored at this value (an indicator, flagged in the output).
        capacity_hours: staffed hours, echoed for charts.
    Returns a ForecastRun-shaped dict: model_kind, predicted_hours, low, high, mae,
        method_comparison, backtest, interval_label, floored_by_known_bookings, capacity_hours.
    """
    if len(series) < 4:
        raise ValueError("need at least 4 weeks for a backtest")
    alpha = float(policy.get(policy.policy_map(policies) if not isinstance(policies, dict) else policies,
                             "forecast.ewma_alpha"))
    predictors = _predictors(alpha)
    results = {name: backtest(series, predictors[name]) for name in METHOD_ORDER}
    best = min(METHOD_ORDER, key=lambda name: (results[name]["mae"], METHOD_ORDER.index(name)))
    predicted = predictors[best](list(series))
    spread = max(r["abs_error"] for r in results[best]["predictions"])
    floored = known_booked_hours is not None and float(known_booked_hours) > predicted
    if floored:
        predicted = float(known_booked_hours)
    return {
        "model_kind": best, "model_version": "baseline_v1", "predicted_hours": round(predicted, 2),
        "low": round(max(0.0, predicted - spread), 2), "high": round(predicted + spread, 2),
        "mae": results[best]["mae"],
        "method_comparison": {name: results[name]["mae"] for name in METHOD_ORDER},
        "backtest": results[best]["predictions"],
        "input_weeks": len(series), "test_span": [4, len(series)],
        "interval_label": "illustrative range (+/- max backtest error), not a calibrated interval",
        "floored_by_known_bookings": floored, "capacity_hours": capacity_hours,
    }


def forecast_resource(demand_rows, resource_id, policies=None, known_booked_hours=None):
    """Forecast next-week requested hours for one resource from weekly demand rows."""
    rows = sorted((r for r in demand_rows if r["resource_id"] == resource_id), key=lambda r: r["week_start"])
    series = [float(as_num(r["requested_hours"])) for r in rows]
    result = forecast_series(series, policies, known_booked_hours,
                             capacity_hours=float(as_num(rows[-1]["staffed_hours"])) if rows else None)
    result.update(resource_id=resource_id, input_window=[rows[0]["week_start"], rows[-1]["week_start"]],
                  signal="requested_hours")
    return result
