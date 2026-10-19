"""moving_average_forecast and the backtest (T-FORE-001)."""
import pytest

from labsync_core.forecast import (backtest, ewma_forecast, forecast_resource, forecast_series,
                                   moving_average_forecast, naive_forecast)


def test_weighted_moving_average():
    assert moving_average_forecast([10, 20, 30]) == pytest.approx((10 + 40 + 90) / 6)
    assert moving_average_forecast([10, 20, 30, 40], weighted=False) == 30
    assert moving_average_forecast([5]) == 5


def test_ewma_and_naive():
    assert ewma_forecast([10, 20], alpha=0.5) == 15
    assert naive_forecast([3, 4, 9]) == 9
    with pytest.raises(ValueError):
        moving_average_forecast([])


def test_fore_001_backtest_never_sees_the_week_it_predicts():
    seen = []

    def spy(train):
        seen.append(list(train))
        return 0.0

    series = [1, 2, 3, 4, 5, 6]
    result = backtest(series, spy)
    assert seen == [[1, 2, 3], [1, 2, 3, 4], [1, 2, 3, 4, 5]]
    assert [r["week_index"] for r in result["predictions"]] == [4, 5, 6]
    assert result["mae"] == pytest.approx((4 + 5 + 6) / 3)


def test_best_method_by_mae_and_illustrative_band():
    out = forecast_series([24, 29, 31, 28, 33, 34])
    assert out["model_kind"] in out["method_comparison"]
    assert out["mae"] == min(out["method_comparison"].values())
    assert out["low"] <= out["predicted_hours"] <= out["high"]
    assert "not a calibrated" in out["interval_label"]


def test_needs_four_weeks():
    with pytest.raises(ValueError):
        forecast_series([1, 2, 3])


def test_known_bookings_floor_the_forecast():
    out = forecast_series([5, 5, 5, 5, 5, 5], known_booked_hours=12)
    assert out["predicted_hours"] == 12 and out["floored_by_known_bookings"]


def test_forecast_from_seeded_demand(seed):
    out = forecast_resource(seed["demand"], "confocal_1", seed["policies"])
    assert out["input_window"] == ["2026-09-21", "2026-10-26"] and out["signal"] == "requested_hours"
    assert out["input_weeks"] == 6 and len(out["backtest"]) == 3
    # Confocal-1 latent demand trends up: the forecast sits above the long-run mean.
    assert out["predicted_hours"] > 30 and out["capacity_hours"] == 40
