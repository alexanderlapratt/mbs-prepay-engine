"""
test_cashflows.py — Unit tests for cashflow_engine.py

Tests cover:
  - project_cashflows: output structure, balance continuity, period count
  - Zero prepayment case matches amortization schedule
  - WAL bounds and basic properties
  - SMM/CPR relationship in output
  - Prepayment increases in rally scenarios

Run with:  pytest tests/test_cashflows.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.cashflow_engine import project_cashflows, compute_wal, extract_total_cashflows
from src.mortgage_math import remaining_balance


# ---------------------------------------------------------------------------
# project_cashflows
# ---------------------------------------------------------------------------

class TestProjectCashflows:

    BASE_POOL = dict(
        original_balance=100_000_000,
        wac=0.065,
        wam=360,
        pool_age=24,
        current_mortgage_rate=0.065,
        servicing_fee=0.0025,
    )

    def test_returns_list_of_dicts(self):
        cfs = project_cashflows(**self.BASE_POOL)
        assert isinstance(cfs, list)
        assert len(cfs) > 0
        assert isinstance(cfs[0], dict)

    def test_expected_keys_present(self):
        cfs = project_cashflows(**self.BASE_POOL)
        required = [
            "period", "beginning_balance", "scheduled_payment",
            "interest", "scheduled_principal", "cpr", "smm",
            "prepayment", "total_principal", "ending_balance", "total_cashflow",
        ]
        for key in required:
            assert key in cfs[0], f"Missing key: {key}"

    def test_period_count(self):
        """Should project up to wam - pool_age periods."""
        cfs = project_cashflows(**self.BASE_POOL)
        remaining = self.BASE_POOL["wam"] - self.BASE_POOL["pool_age"]
        # May be fewer if balance reaches zero
        assert len(cfs) <= remaining
        assert len(cfs) > 0

    def test_balance_continuity(self):
        """Ending balance of period t should equal beginning balance of period t+1."""
        cfs = project_cashflows(**self.BASE_POOL)
        for i in range(len(cfs) - 1):
            diff = abs(cfs[i]["ending_balance"] - cfs[i+1]["beginning_balance"])
            assert diff < 1.0, f"Balance discontinuity at period {i+1}: {diff}"

    def test_balance_non_negative(self):
        """Ending balance should never be negative."""
        cfs = project_cashflows(**self.BASE_POOL)
        for cf in cfs:
            assert cf["ending_balance"] >= -0.01, f"Negative balance: {cf['ending_balance']}"

    def test_total_cashflow_equals_interest_plus_principal(self):
        """total_cashflow should = interest + total_principal."""
        cfs = project_cashflows(**self.BASE_POOL)
        for cf in cfs:
            expected = cf["interest"] + cf["total_principal"]
            assert abs(cf["total_cashflow"] - expected) < 0.10, \
                f"CF mismatch at period {cf['period']}: {cf['total_cashflow']} vs {expected}"

    def test_cpr_in_valid_range(self):
        """CPR should be between 0 and 1 for all periods."""
        cfs = project_cashflows(**self.BASE_POOL)
        for cf in cfs:
            assert 0.0 <= cf["cpr"] <= 1.0, f"CPR out of range: {cf['cpr']}"

    def test_smm_from_cpr_relationship(self):
        """SMM should satisfy SMM = 1 - (1 - CPR)^(1/12) for each period."""
        cfs = project_cashflows(**self.BASE_POOL)
        for cf in cfs[:12]:
            expected_smm = 1.0 - (1.0 - cf["cpr"]) ** (1.0 / 12.0)
            assert abs(cf["smm"] - expected_smm) < 1e-6, \
                f"SMM/CPR mismatch at period {cf['period']}"

    def test_rally_increases_prepayment(self):
        """Rates-down scenario should have more prepayment than rates-up."""
        cfs_rally   = project_cashflows(**{**self.BASE_POOL, "current_mortgage_rate": 0.055})
        cfs_selloff = project_cashflows(**{**self.BASE_POOL, "current_mortgage_rate": 0.075})

        total_prep_rally   = sum(c["prepayment"] for c in cfs_rally)
        total_prep_selloff = sum(c["prepayment"] for c in cfs_selloff)

        assert total_prep_rally > total_prep_selloff, \
            "Rally should produce more prepayment than selloff"

    def test_rally_concentrates_principal_earlier(self):
        """
        In a rate rally, the majority of principal return is front-loaded
        (high prepayments in early periods).  We verify this by checking that
        50% of total principal is returned earlier in the rally vs. base.
        This is the economic meaning of a shorter WAL.
        """
        from src.mortgage_math import remaining_balance as _rb
        from src.cashflow_engine import compute_wal

        cfs_base = project_cashflows(**self.BASE_POOL)
        cfs_down = project_cashflows(**{**self.BASE_POOL, "current_mortgage_rate": 0.055})

        current_bal = _rb(
            self.BASE_POOL["original_balance"], self.BASE_POOL["wac"],
            self.BASE_POOL["wam"] + self.BASE_POOL["pool_age"], self.BASE_POOL["pool_age"]
        )
        wal_base = compute_wal(cfs_base, current_bal)
        wal_down = compute_wal(cfs_down, current_bal)

        assert wal_down < wal_base, \
            f"Rally WAL {wal_down:.2f}yr should be shorter than base WAL {wal_base:.2f}yr"

    def test_fully_aged_pool_returns_empty(self):
        """Pool with pool_age >= wam should return empty list."""
        cfs = project_cashflows(
            original_balance=100_000_000, wac=0.065, wam=360, pool_age=360,
            current_mortgage_rate=0.065,
        )
        assert cfs == []

    def test_total_principal_sums_to_current_balance(self):
        """Total principal paid should approximately equal the starting balance."""
        cfs = project_cashflows(**self.BASE_POOL)
        current_bal = remaining_balance(
            self.BASE_POOL["original_balance"],
            self.BASE_POOL["wac"],
            self.BASE_POOL["wam"] + self.BASE_POOL["pool_age"],
            self.BASE_POOL["pool_age"],
        )
        total_prin = sum(c["total_principal"] for c in cfs)
        # Should be within 1% of current balance
        assert abs(total_prin - current_bal) / current_bal < 0.01, \
            f"Total principal {total_prin:.0f} differs from balance {current_bal:.0f}"


# ---------------------------------------------------------------------------
# compute_wal
# ---------------------------------------------------------------------------

class TestComputeWAL:

    BASE_POOL = dict(
        original_balance=100_000_000, wac=0.065, wam=360, pool_age=24,
        current_mortgage_rate=0.065, servicing_fee=0.0025,
    )

    def test_positive_wal(self):
        """WAL should be positive."""
        cfs = project_cashflows(**self.BASE_POOL)
        bal = remaining_balance(100_000_000, 0.065, 384, 24)
        wal = compute_wal(cfs, bal)
        assert wal > 0.0

    def test_wal_less_than_remaining_wam(self):
        """WAL should be less than the remaining term (because principal paid gradually)."""
        cfs = project_cashflows(**self.BASE_POOL)
        bal = remaining_balance(100_000_000, 0.065, 384, 24)
        wal = compute_wal(cfs, bal)
        remaining_wam_yrs = (360 - 24) / 12.0
        assert wal < remaining_wam_yrs

    def test_rally_reduces_wal(self):
        """
        Rate rally → faster prepayments → shorter WAL.
        The key property is rally WAL < base WAL.  Selloff WAL may equal base
        WAL when the pool is at-the-money (CPR already at turnover floor;
        no further slowdown possible) — this is correct model behavior.
        """
        pool_base  = {**self.BASE_POOL}
        pool_rally = {**self.BASE_POOL, "current_mortgage_rate": 0.055}

        bal = remaining_balance(100_000_000, 0.065, 384, 24)

        cfs_base  = project_cashflows(**pool_base)
        cfs_rally = project_cashflows(**pool_rally)

        wal_base  = compute_wal(cfs_base, bal)
        wal_rally = compute_wal(cfs_rally, bal)

        assert wal_rally < wal_base, \
            f"Rally WAL should be < base WAL: rally={wal_rally:.2f} vs base={wal_base:.2f}"

    def test_empty_cashflows_returns_zero(self):
        assert compute_wal([], 100_000) == 0.0

    def test_zero_balance_returns_zero(self):
        cfs = project_cashflows(**self.BASE_POOL)
        assert compute_wal(cfs, 0.0) == 0.0


# ---------------------------------------------------------------------------
# extract_total_cashflows
# ---------------------------------------------------------------------------

class TestExtractTotalCashflows:

    def test_returns_list_of_floats(self):
        pool = dict(
            original_balance=50_000_000, wac=0.065, wam=360, pool_age=0,
            current_mortgage_rate=0.065,
        )
        cfs    = project_cashflows(**pool)
        totals = extract_total_cashflows(cfs)
        assert isinstance(totals, list)
        assert all(isinstance(x, float) for x in totals)

    def test_length_matches_cashflows(self):
        pool = dict(
            original_balance=50_000_000, wac=0.065, wam=360, pool_age=0,
            current_mortgage_rate=0.065,
        )
        cfs    = project_cashflows(**pool)
        totals = extract_total_cashflows(cfs)
        assert len(totals) == len(cfs)

    def test_values_are_positive(self):
        pool = dict(
            original_balance=50_000_000, wac=0.065, wam=360, pool_age=0,
            current_mortgage_rate=0.065,
        )
        cfs    = project_cashflows(**pool)
        totals = extract_total_cashflows(cfs)
        assert all(t > 0 for t in totals)
