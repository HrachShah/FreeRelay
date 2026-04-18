"""
Tests — Budget Forecaster
============================
Verify EWMA and budget exhaustion prediction per spec §10.
"""


from freerelay.core.resilience.budget import BudgetForecaster


class TestBudgetForecaster:
    def test_default_score_is_full(self) -> None:
        forecaster = BudgetForecaster()
        assert forecaster.get_budget_score("groq") == 1.0

    def test_unlimited_never_exhausted(self) -> None:
        forecaster = BudgetForecaster()
        # No daily limit set
        forecaster.record_tokens("groq", 1_000_000)
        assert not forecaster.is_budget_exhausted("groq")
        assert forecaster.get_budget_score("groq") == 1.0

    def test_score_decreases_with_usage(self) -> None:
        forecaster = BudgetForecaster()
        forecaster.set_daily_limit("groq", 100_000)

        forecaster.record_tokens("groq", 50_000)
        score = forecaster.get_budget_score("groq")
        assert 0.49 < score < 0.51  # ~0.5

    def test_exhausted_when_limit_reached(self) -> None:
        forecaster = BudgetForecaster(safety_margin=1000)
        forecaster.set_daily_limit("groq", 100_000)

        forecaster.record_tokens("groq", 100_000)
        assert forecaster.is_budget_exhausted("groq")
        assert forecaster.get_budget_score("groq") == 0.0

    def test_reset_daily(self) -> None:
        forecaster = BudgetForecaster()
        forecaster.set_daily_limit("groq", 100_000)
        forecaster.record_tokens("groq", 80_000)

        forecaster.reset_daily("groq")
        assert forecaster.get_budget_score("groq") == 1.0

    def test_stats_output(self) -> None:
        forecaster = BudgetForecaster()
        forecaster.set_daily_limit("groq", 500_000)
        forecaster.record_tokens("groq", 10_000)

        stats = forecaster.get_stats("groq")
        assert stats["provider"] == "groq"
        assert stats["tokens_used_today"] == 10_000
        assert stats["daily_limit"] == 500_000
        assert isinstance(stats["budget_score"], float)
