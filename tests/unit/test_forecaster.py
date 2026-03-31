"""
Tests — EWMA Forecaster
==========================
Verify EWMA forecasting math per spec §10.
"""

from freerelay.core.resilience.forecast import EWMAForecaster, ForecastSnapshot


class TestEWMAForecaster:
    def test_initial_forecast_no_limit(self) -> None:
        forecaster = EWMAForecaster()
        snap = forecaster.get_forecast("groq", 0, None)
        assert snap.provider == "groq"
        assert snap.budget_ratio == 1.0
        assert snap.ewma_rate == 0.0

    def test_forecast_with_limit(self) -> None:
        forecaster = EWMAForecaster()
        snap = forecaster.get_forecast("groq", 50000, 100000)
        assert snap.budget_ratio == 0.5
        assert snap.projected_remaining == 40000  # 50000 - 10000 safety margin

    def test_exhausted_budget(self) -> None:
        forecaster = EWMAForecaster()
        snap = forecaster.get_forecast("groq", 100000, 100000)
        assert snap.budget_ratio == 0.0
        assert snap.minutes_until_exhaustion == 0

    def test_should_route_away_no_limit(self) -> None:
        forecaster = EWMAForecaster()
        assert not forecaster.should_route_away("groq", 0, None)

    def test_should_route_away_exhausted(self) -> None:
        forecaster = EWMAForecaster()
        assert forecaster.should_route_away("groq", 100000, 100000)

    def test_should_route_away_below_safety_margin(self) -> None:
        forecaster = EWMAForecaster(safety_margin_tokens=10000)
        assert forecaster.should_route_away("groq", 95000, 100000)

    def test_should_not_route_away_with_budget(self) -> None:
        forecaster = EWMAForecaster(safety_margin_tokens=10000)
        assert not forecaster.should_route_away("groq", 50000, 100000)

    def test_forecast_snapshot_fields(self) -> None:
        snap = ForecastSnapshot(
            provider="groq",
            current_rate=100.0,
            ewma_rate=90.0,
            projected_remaining=50000,
            minutes_until_exhaustion=10.0,
            budget_ratio=0.5,
        )
        assert snap.provider == "groq"
        assert snap.current_rate == 100.0
        assert snap.ewma_rate == 90.0
        assert snap.projected_remaining == 50000
        assert snap.minutes_until_exhaustion == 10.0
        assert snap.budget_ratio == 0.5
