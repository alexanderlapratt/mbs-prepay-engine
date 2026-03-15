"""
test_cpr_model.py — Unit tests for cpr_model.py

Tests cover:
  - Refi incentive CPR (S-curve behavior)
  - Seasoning ramp
  - Burnout adjustment
  - Turnover CPR
  - Seasonality multipliers
  - Combined compute_cpr (bounds, monotonicity, driver interactions)
  - CPR driver decomposition

Run with:  pytest tests/test_cpr_model.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.cpr_model import (
    refi_incentive_cpr,
    seasoning_multiplier,
    burnout_adjustment,
    turnover_cpr,
    seasonality_adjustment,
    compute_cpr,
    cpr_driver_decomposition,
)
from src.config import BASELINE_CPR, MAX_CPR


# ---------------------------------------------------------------------------
# refi_incentive_cpr
# ---------------------------------------------------------------------------

class TestRefiIncentiveCPR:

    def test_at_the_money_is_low(self):
        """When WAC == market rate, refi incentive CPR should be near zero."""
        cpr = refi_incentive_cpr(0.065, 0.065)
        assert cpr < 0.02, f"At-the-money CPR should be near 0, got {cpr:.4f}"

    def test_deep_in_the_money_is_high(self):
        """When pool is 200bp in-the-money, refi CPR should be substantial."""
        cpr = refi_incentive_cpr(0.08, 0.06)   # 200bp incentive
        assert cpr > 0.15, f"200bp ITM CPR should be >15%, got {cpr:.4f}"

    def test_out_of_the_money_near_zero(self):
        """When market rate > WAC (no refi incentive), CPR should be near zero."""
        cpr = refi_incentive_cpr(0.05, 0.08)   # rates above coupon
        assert cpr < 0.02

    def test_monotonic_in_incentive(self):
        """CPR should increase as the refi incentive increases."""
        wac = 0.07
        rates = [0.09, 0.075, 0.07, 0.065, 0.06, 0.055, 0.05]
        cprs  = [refi_incentive_cpr(wac, r) for r in rates]
        for i in range(len(cprs) - 1):
            assert cprs[i] <= cprs[i+1], f"CPR not monotonic at rates[{i}]={rates[i]}"

    def test_multiplier_scales_linearly(self):
        """Doubling the refi multiplier should increase (not necessarily double) CPR."""
        base  = refi_incentive_cpr(0.075, 0.06, refi_multiplier=1.0)
        scaled = refi_incentive_cpr(0.075, 0.06, refi_multiplier=2.0)
        assert scaled > base

    def test_non_negative(self):
        """CPR should never be negative."""
        for rate in [0.03, 0.05, 0.065, 0.08, 0.10, 0.12]:
            cpr = refi_incentive_cpr(0.065, rate)
            assert cpr >= 0.0


# ---------------------------------------------------------------------------
# seasoning_multiplier
# ---------------------------------------------------------------------------

class TestSeasoningMultiplier:

    def test_new_pool_is_zero(self):
        """Age 0 months → 0% of CPR."""
        assert seasoning_multiplier(0, 30) == 0.0

    def test_full_seasoning_is_one(self):
        """Age >= ramp_months → 100% multiplier."""
        assert seasoning_multiplier(30, 30) == 1.0
        assert seasoning_multiplier(60, 30) == 1.0

    def test_halfway_is_half(self):
        """Age 15 of 30 months ramp → 50%."""
        mult = seasoning_multiplier(15, 30)
        assert abs(mult - 0.5) < 1e-9

    def test_linear_ramp(self):
        """Multiplier should increase linearly."""
        mults = [seasoning_multiplier(t, 30) for t in range(0, 31)]
        diffs = [mults[i+1] - mults[i] for i in range(len(mults)-1)]
        for d in diffs:
            assert abs(d - 1/30) < 1e-6


# ---------------------------------------------------------------------------
# burnout_adjustment
# ---------------------------------------------------------------------------

class TestBurnoutAdjustment:

    def test_no_burnout(self):
        """Factor = 1.0 → no dampening."""
        assert burnout_adjustment(1.0) == 1.0

    def test_full_burnout(self):
        """Factor = 0.0 → pool is fully burned out."""
        assert burnout_adjustment(0.0) == 0.0

    def test_partial_burnout(self):
        """Factor = 0.6 → 40% dampening."""
        assert abs(burnout_adjustment(0.6) - 0.6) < 1e-9

    def test_clamps_above_one(self):
        """Values > 1 should be clamped to 1."""
        assert burnout_adjustment(1.5) == 1.0

    def test_clamps_below_zero(self):
        """Values < 0 should be clamped to 0."""
        assert burnout_adjustment(-0.3) == 0.0


# ---------------------------------------------------------------------------
# turnover_cpr
# ---------------------------------------------------------------------------

class TestTurnoverCPR:

    def test_baseline_equals_config(self):
        """Default turnover CPR should equal the configured baseline."""
        cpr = turnover_cpr(1.0, BASELINE_CPR)
        assert abs(cpr - BASELINE_CPR) < 1e-9

    def test_scaled_by_factor(self):
        """Doubling the turnover factor should double the CPR."""
        base  = turnover_cpr(1.0, 0.05)
        scaled = turnover_cpr(2.0, 0.05)
        assert abs(scaled / base - 2.0) < 1e-9

    def test_zero_factor_is_zero(self):
        assert turnover_cpr(0.0, 0.05) == 0.0


# ---------------------------------------------------------------------------
# seasonality_adjustment
# ---------------------------------------------------------------------------

class TestSeasonalityAdjustment:

    def test_summer_higher_than_winter(self):
        """May/June should have higher multiplier than January."""
        assert seasonality_adjustment(5) > seasonality_adjustment(1)
        assert seasonality_adjustment(6) > seasonality_adjustment(12)

    def test_valid_for_all_months(self):
        """Should return a positive value for all 12 months."""
        for m in range(1, 13):
            assert seasonality_adjustment(m) > 0.0

    def test_unknown_month_returns_one(self):
        """Month 0 or 13 should return 1.0 (neutral)."""
        assert seasonality_adjustment(0) == 1.0
        assert seasonality_adjustment(13) == 1.0


# ---------------------------------------------------------------------------
# compute_cpr (integration)
# ---------------------------------------------------------------------------

class TestComputeCPR:

    def test_within_bounds(self):
        """CPR should always be within [baseline, max_cpr]."""
        for market_rate in [0.04, 0.06, 0.065, 0.08, 0.10]:
            cpr = compute_cpr(
                wac=0.065, current_mortgage_rate=market_rate,
                pool_age_months=24, baseline_cpr=0.04, max_cpr=0.60,
            )
            assert 0.0 <= cpr <= 0.60, f"CPR {cpr} out of bounds at rate {market_rate}"

    def test_rally_increases_cpr(self):
        """CPR should be higher when rates are below WAC (rally scenario)."""
        cpr_base   = compute_cpr(0.065, 0.065, 24)
        cpr_rally  = compute_cpr(0.065, 0.055, 24)
        assert cpr_rally > cpr_base

    def test_selloff_reduces_cpr(self):
        """CPR should be lower when rates rise above WAC."""
        cpr_base    = compute_cpr(0.065, 0.065, 24)
        cpr_selloff = compute_cpr(0.065, 0.080, 24)
        assert cpr_selloff <= cpr_base

    def test_unseasoned_pool_lower_cpr(self):
        """Age-0 pool should have lower CPR than age-30 pool (ramp effect)."""
        cpr_new  = compute_cpr(0.065, 0.055, pool_age_months=0)
        cpr_aged = compute_cpr(0.065, 0.055, pool_age_months=30)
        assert cpr_new < cpr_aged

    def test_burnout_reduces_cpr(self):
        """Burned-out pool should have lower CPR than fresh pool, given same incentive."""
        cpr_fresh  = compute_cpr(0.075, 0.060, 30, burnout_factor=1.0)
        cpr_burned = compute_cpr(0.075, 0.060, 30, burnout_factor=0.5)
        assert cpr_burned < cpr_fresh

    def test_large_loan_faster_than_small(self):
        """Large loan bucket should prepay faster than small."""
        cpr_large = compute_cpr(0.07, 0.06, 30, loan_size_bucket="large")
        cpr_small = compute_cpr(0.07, 0.06, 30, loan_size_bucket="small")
        assert cpr_large > cpr_small

    def test_high_geo_faster_than_low(self):
        """High prepay geography should have faster CPR."""
        cpr_high = compute_cpr(0.07, 0.06, 30, geography_bucket="high")
        cpr_low  = compute_cpr(0.07, 0.06, 30, geography_bucket="low")
        assert cpr_high > cpr_low


# ---------------------------------------------------------------------------
# cpr_driver_decomposition
# ---------------------------------------------------------------------------

class TestCPRDriverDecomposition:

    def test_returns_required_keys(self):
        decomp = cpr_driver_decomposition(
            wac=0.065, current_mortgage_rate=0.055, pool_age_months=24
        )
        expected_keys = [
            "incentive_bp", "refi_contribution", "turnover_contribution",
            "seasoning_mult", "burnout_adj", "loan_size_mult",
            "geo_mult", "calendar_mult", "total_cpr",
        ]
        for key in expected_keys:
            assert key in decomp, f"Missing key: {key}"

    def test_total_cpr_non_negative(self):
        decomp = cpr_driver_decomposition(0.065, 0.08, 10)
        assert decomp["total_cpr"] >= 0.0

    def test_incentive_positive_when_itm(self):
        """When WAC > market rate, incentive should be positive (in-the-money)."""
        decomp = cpr_driver_decomposition(0.07, 0.06, 24)
        assert decomp["incentive_bp"] > 0

    def test_incentive_negative_when_otm(self):
        """When WAC < market rate, incentive should be negative."""
        decomp = cpr_driver_decomposition(0.06, 0.08, 24)
        assert decomp["incentive_bp"] < 0
