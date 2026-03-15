"""
test_mortgage_math.py — Unit tests for mortgage_math.py

Tests cover:
  - Scheduled payment (known values, edge cases)
  - Monthly interest
  - Net coupon
  - Scheduled principal
  - Remaining balance (closed-form vs iterative)
  - Amortization schedule totals
  - Price from cash flows

Run with:  pytest tests/test_mortgage_math.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import math
from src.mortgage_math import (
    scheduled_payment,
    monthly_interest,
    net_coupon,
    scheduled_principal,
    remaining_balance,
    amortization_schedule,
    price_from_cashflows,
)


# ---------------------------------------------------------------------------
# scheduled_payment
# ---------------------------------------------------------------------------

class TestScheduledPayment:

    def test_known_value_30yr_6pct(self):
        """
        $100,000 loan at 6.0% for 30 years.
        Standard reference: P ≈ $599.55/month.
        """
        pmt = scheduled_payment(100_000, 0.06, 360)
        assert abs(pmt - 599.55) < 0.10, f"Expected ~$599.55, got {pmt:.2f}"

    def test_known_value_15yr(self):
        """$200,000 at 5.0% for 15 years ≈ $1,581.59/month."""
        pmt = scheduled_payment(200_000, 0.05, 180)
        assert abs(pmt - 1_581.59) < 0.50

    def test_zero_rate_is_principal_only(self):
        """At 0% rate, payment = balance / term."""
        pmt = scheduled_payment(120_000, 0.0, 120)
        assert abs(pmt - 1_000.0) < 0.01

    def test_zero_wam_returns_zero(self):
        """WAM of 0 should not raise, should return 0."""
        assert scheduled_payment(100_000, 0.06, 0) == 0.0

    def test_larger_balance_scales_linearly(self):
        """Doubling the balance should double the payment (same rate/term)."""
        p1 = scheduled_payment(100_000, 0.065, 360)
        p2 = scheduled_payment(200_000, 0.065, 360)
        assert abs(p2 / p1 - 2.0) < 1e-6

    def test_higher_rate_increases_payment(self):
        """Higher coupon → higher payment for same balance/term."""
        p_low  = scheduled_payment(100_000, 0.04, 360)
        p_high = scheduled_payment(100_000, 0.08, 360)
        assert p_high > p_low

    def test_shorter_term_increases_payment(self):
        """Shorter WAM → higher payment (less time to amortize)."""
        p_30yr = scheduled_payment(200_000, 0.065, 360)
        p_15yr = scheduled_payment(200_000, 0.065, 180)
        assert p_15yr > p_30yr


# ---------------------------------------------------------------------------
# monthly_interest
# ---------------------------------------------------------------------------

class TestMonthlyInterest:

    def test_basic_calculation(self):
        """$100,000 at 6.0% gross → $500/month interest."""
        interest = monthly_interest(100_000, 0.06)
        assert abs(interest - 500.0) < 0.01

    def test_zero_balance(self):
        assert monthly_interest(0.0, 0.065) == 0.0

    def test_zero_rate(self):
        assert monthly_interest(100_000, 0.0) == 0.0

    def test_proportional_to_balance(self):
        """Interest should be proportional to balance."""
        i1 = monthly_interest(100_000, 0.072)
        i2 = monthly_interest(200_000, 0.072)
        assert abs(i2 / i1 - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# net_coupon
# ---------------------------------------------------------------------------

class TestNetCoupon:

    def test_strips_servicing_fee(self):
        """6.5% WAC minus 25bp = 6.25% net coupon."""
        nc = net_coupon(0.065, 0.0025)
        assert abs(nc - 0.0625) < 1e-9

    def test_zero_fee(self):
        """Zero servicing fee → gross = net."""
        assert net_coupon(0.065, 0.0) == 0.065

    def test_large_fee(self):
        """Fee larger than WAC results in negative net coupon (edge case)."""
        nc = net_coupon(0.065, 0.08)
        assert nc < 0.0


# ---------------------------------------------------------------------------
# scheduled_principal
# ---------------------------------------------------------------------------

class TestScheduledPrincipal:

    def test_positive(self):
        """Scheduled principal should always be positive for standard inputs."""
        sp = scheduled_principal(100_000, 0.06, 360)
        assert sp > 0.0

    def test_payment_equals_interest_plus_principal(self):
        """P = I + SchedPrin (for gross coupon)."""
        bal = 250_000
        wac = 0.065
        wam = 360
        pmt = scheduled_payment(bal, wac, wam)
        interest = monthly_interest(bal, wac)
        sp = scheduled_principal(bal, wac, wam)
        assert abs(pmt - (interest + sp)) < 0.01

    def test_grows_over_time(self):
        """Scheduled principal should be larger in period 2 than period 1."""
        bal = 400_000
        wac = 0.07
        wam = 360
        sp1 = scheduled_principal(bal, wac, wam)
        # After one payment the balance is slightly lower
        new_bal = bal - sp1
        sp2 = scheduled_principal(new_bal, wac, wam - 1)
        assert sp2 >= sp1


# ---------------------------------------------------------------------------
# remaining_balance
# ---------------------------------------------------------------------------

class TestRemainingBalance:

    def test_at_origination(self):
        """At period 0, remaining balance = original balance."""
        bal = remaining_balance(100_000, 0.06, 360, 0)
        assert abs(bal - 100_000) < 0.01

    def test_at_maturity(self):
        """At period N, remaining balance ≈ 0."""
        bal = remaining_balance(100_000, 0.06, 360, 360)
        assert abs(bal) < 1.0

    def test_decreases_monotonically(self):
        """Balance should decrease each period (no prepayments)."""
        balances = [remaining_balance(200_000, 0.065, 360, t) for t in range(0, 361, 12)]
        for i in range(len(balances) - 1):
            assert balances[i] >= balances[i+1], f"Balance increased at period {i*12}"

    def test_halfway_through_30yr(self):
        """After 15 years of a 30yr loan, more than 50% of balance remains."""
        bal_15yr = remaining_balance(100_000, 0.065, 360, 180)
        # Due to front-loaded interest, more than half the balance remains
        assert bal_15yr > 50_000

    def test_zero_rate(self):
        """Zero-rate loan: balance declines linearly."""
        bal = remaining_balance(120_000, 0.0, 120, 60)
        assert abs(bal - 60_000) < 1.0


# ---------------------------------------------------------------------------
# amortization_schedule
# ---------------------------------------------------------------------------

class TestAmortizationSchedule:

    def test_length(self):
        """Schedule should have wam entries."""
        sched = amortization_schedule(100_000, 0.065, 360)
        assert len(sched) == 360

    def test_period_numbers(self):
        """Periods should be numbered 1 through wam."""
        sched = amortization_schedule(100_000, 0.065, 60)
        assert sched[0]["period"] == 1
        assert sched[-1]["period"] == 60

    def test_final_balance_near_zero(self):
        """Ending balance of final period should be ≈ 0."""
        sched = amortization_schedule(100_000, 0.065, 360)
        assert sched[-1]["ending_balance"] < 1.0

    def test_total_principal_equals_original_balance(self):
        """Sum of all scheduled principal should equal the original balance."""
        balance = 250_000
        sched = amortization_schedule(balance, 0.07, 360)
        total_prin = sum(p["scheduled_principal"] for p in sched)
        assert abs(total_prin - balance) < 10.0

    def test_beginning_balance_continuity(self):
        """Beginning balance of period t = ending balance of period t-1."""
        sched = amortization_schedule(100_000, 0.065, 360)
        for i in range(1, len(sched)):
            assert abs(sched[i]["beginning_balance"] - sched[i-1]["ending_balance"]) < 0.05


# ---------------------------------------------------------------------------
# price_from_cashflows
# ---------------------------------------------------------------------------

class TestPriceFromCashflows:

    def test_positive_price(self):
        """Price should be positive for any valid cash-flow stream."""
        cfs = [1000.0] * 12
        price = price_from_cashflows(cfs, 0.06)
        assert price > 0.0

    def test_higher_rate_lower_price(self):
        """Higher discount rate → lower present value."""
        cfs = [1000.0] * 120
        p_low  = price_from_cashflows(cfs, 0.03)
        p_high = price_from_cashflows(cfs, 0.08)
        assert p_high < p_low

    def test_zero_rate_sums_to_cashflows(self):
        """At 0% discount rate, price = sum of cash flows."""
        cfs   = [500.0] * 10
        price = price_from_cashflows(cfs, 0.0)
        assert abs(price - sum(cfs)) < 0.01

    def test_single_cashflow(self):
        """Single cash flow at period 1 discounted by one month."""
        r = 0.06 / 12
        cf = 1_000_000
        price = price_from_cashflows([cf], 0.06)
        expected = cf / (1 + r)
        assert abs(price - expected) < 0.01
