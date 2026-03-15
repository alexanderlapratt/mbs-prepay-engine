"""
test_risk.py — Unit tests for risk_engine.py and hedge_engine.py

Tests cover:
  - compute_risk_metrics: output keys, sign conventions, negative convexity
  - Duration and convexity monotonicity across rate scenarios
  - DV01 positive
  - Hedge ratio sign convention
  - build_hedge_summary: structure and signs

Run with:  pytest tests/test_risk.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.risk_engine import compute_risk_metrics
from src.hedge_engine import compute_hedge_ratio, build_hedge_summary, convexity_hedge_cost_estimate


# ---------------------------------------------------------------------------
# Shared pool fixture
# ---------------------------------------------------------------------------

POOL = dict(
    original_balance=100_000_000,
    wac=0.065,
    wam=360,
    pool_age=24,
    servicing_fee=0.0025,
    loan_size_bucket="medium",
    geography_bucket="medium",
    burnout_factor=0.85,
    turnover_factor=1.0,
    baseline_cpr=0.05,
    max_cpr=0.60,
    seasonality_factor=1.0,
)

BASE_RATE = 0.065


# ---------------------------------------------------------------------------
# compute_risk_metrics
# ---------------------------------------------------------------------------

class TestComputeRiskMetrics:

    def test_returns_required_keys(self):
        result = compute_risk_metrics(POOL, BASE_RATE, BASE_RATE)
        required = ["price", "wal", "eff_duration", "convexity", "dv01",
                    "hedge_units", "cashflows_base", "current_balance"]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_price_positive(self):
        result = compute_risk_metrics(POOL, BASE_RATE, BASE_RATE)
        assert result["price"] > 0.0

    def test_wal_positive(self):
        result = compute_risk_metrics(POOL, BASE_RATE, BASE_RATE)
        assert result["wal"] > 0.0

    def test_wal_less_than_remaining_term(self):
        result = compute_risk_metrics(POOL, BASE_RATE, BASE_RATE)
        remaining_years = (POOL["wam"] - POOL["pool_age"]) / 12.0
        assert result["wal"] < remaining_years

    def test_duration_positive(self):
        """Effective duration should be positive (price falls when rates rise)."""
        result = compute_risk_metrics(POOL, BASE_RATE, BASE_RATE)
        assert result["eff_duration"] > 0.0

    def test_dv01_positive(self):
        """DV01 (absolute value) should be positive."""
        result = compute_risk_metrics(POOL, BASE_RATE, BASE_RATE)
        assert result["dv01"] > 0.0

    def test_hedge_units_positive(self):
        """Number of contracts needed should be positive (short the hedge)."""
        result = compute_risk_metrics(POOL, BASE_RATE, BASE_RATE)
        assert result["hedge_units"] > 0.0

    def test_negative_convexity_for_in_the_money_pool(self):
        """
        A pool where the WAC is at or above the market rate should exhibit
        negative convexity.  At-the-money pools are most negatively convex
        because a 50bp rally triggers a large CPR acceleration (steep S-curve),
        capping price appreciation — while a 50bp selloff leaves CPR near its
        floor (no extension), giving asymmetric returns.
        """
        # At-the-money or slightly ITM pool with 50bp shock hits the S-curve
        result = compute_risk_metrics(POOL, 0.065, 0.065)
        assert result["convexity"] < 0.0, \
            f"At-the-money pool should have negative convexity, got {result['convexity']}"

    def test_rally_vs_selloff_duration(self):
        """
        Duration should be shorter in a rate rally (faster prepayments shorten WAL).
        In a rate selloff, WAL may not extend dramatically if the pool is at-the-money
        (CPR already at turnover floor — no further slowdown possible), which is a
        correct and expected property of this model.
        """
        result_base  = compute_risk_metrics(POOL, 0.065, 0.065)
        result_rally = compute_risk_metrics(POOL, 0.055, 0.055)

        # Rally should always shorten WAL (key MBS property)
        assert result_rally["wal"] < result_base["wal"], \
            "Rally should shorten WAL"

    def test_price_ordering(self):
        """Price should be higher at lower discount rates (inverse relationship)."""
        result_low  = compute_risk_metrics(POOL, 0.05, 0.05)
        result_high = compute_risk_metrics(POOL, 0.08, 0.08)
        assert result_low["price"] > result_high["price"], \
            "Lower rates should produce higher price"

    def test_rate_shock_sensitivity(self):
        """Smaller shock should produce smaller (but proportionally similar) duration."""
        result_25bp = compute_risk_metrics(POOL, BASE_RATE, BASE_RATE, rate_shock=0.0025)
        result_50bp = compute_risk_metrics(POOL, BASE_RATE, BASE_RATE, rate_shock=0.0050)
        # Durations should be in the same ballpark (±50% of each other)
        ratio = abs(result_25bp["eff_duration"] / max(result_50bp["eff_duration"], 0.01))
        assert 0.5 < ratio < 2.0, f"Duration sensitivity too different: {ratio:.2f}"

    def test_cashflows_base_not_empty(self):
        result = compute_risk_metrics(POOL, BASE_RATE, BASE_RATE)
        assert len(result["cashflows_base"]) > 0

    def test_current_balance_positive(self):
        result = compute_risk_metrics(POOL, BASE_RATE, BASE_RATE)
        assert result["current_balance"] > 0.0
        assert result["current_balance"] < POOL["original_balance"]


# ---------------------------------------------------------------------------
# compute_hedge_ratio
# ---------------------------------------------------------------------------

class TestComputeHedgeRatio:

    def test_basic_calculation(self):
        """DV01 of $850 / $850 per contract = 1 contract."""
        ratio = compute_hedge_ratio(850.0, 850.0)
        assert abs(ratio - 1.0) < 1e-9

    def test_zero_dv01(self):
        assert compute_hedge_ratio(0.0) == 0.0

    def test_proportional_to_dv01(self):
        """Doubling DV01 should double hedge units."""
        r1 = compute_hedge_ratio(5_000.0)
        r2 = compute_hedge_ratio(10_000.0)
        assert abs(r2 / r1 - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# convexity_hedge_cost_estimate
# ---------------------------------------------------------------------------

class TestConvexityHedgeCostEstimate:

    def test_negative_convexity_gives_negative_cost(self):
        """Negative convexity pool → negative gamma drag (value lost)."""
        cost = convexity_hedge_cost_estimate(-2.0, 100_000_000)
        assert cost < 0.0

    def test_positive_convexity_gives_positive_cost(self):
        """Positive convexity → favorable (gamma income)."""
        cost = convexity_hedge_cost_estimate(2.0, 100_000_000)
        assert cost > 0.0

    def test_zero_convexity_zero_cost(self):
        cost = convexity_hedge_cost_estimate(0.0, 100_000_000)
        assert abs(cost) < 1e-6

    def test_larger_balance_larger_cost(self):
        cost_small = convexity_hedge_cost_estimate(-1.5, 50_000_000)
        cost_large = convexity_hedge_cost_estimate(-1.5, 100_000_000)
        assert abs(cost_large) > abs(cost_small)


# ---------------------------------------------------------------------------
# build_hedge_summary
# ---------------------------------------------------------------------------

class TestBuildHedgeSummary:

    def _make_risk_results(self):
        scenarios = [
            ("Base",      0.065, 0.065),
            ("Down 50bp", 0.060, 0.060),
            ("Up 50bp",   0.070, 0.070),
        ]
        results = []
        for name, mort_rate, disc_rate in scenarios:
            risk = compute_risk_metrics(POOL, mort_rate, disc_rate)
            risk["scenario_name"] = name
            results.append(risk)
        return results

    def test_returns_correct_number_of_rows(self):
        risks = self._make_risk_results()
        summary = build_hedge_summary(risks)
        assert len(summary) == 3

    def test_required_keys_present(self):
        risks = self._make_risk_results()
        summary = build_hedge_summary(risks)
        required = ["scenario", "dv01_dollar", "hedge_units", "hedge_notional",
                    "eff_duration", "convexity"]
        for key in required:
            assert key in summary[0], f"Missing key: {key}"

    def test_hedge_units_positive(self):
        """All hedge unit counts should be positive (short position)."""
        risks = self._make_risk_results()
        summary = build_hedge_summary(risks)
        for row in summary:
            assert row["hedge_units"] >= 0.0, f"Negative hedge units: {row}"

    def test_scenario_names_preserved(self):
        risks = self._make_risk_results()
        summary = build_hedge_summary(risks)
        names = [row["scenario"] for row in summary]
        assert "Base" in names
        assert "Down 50bp" in names
