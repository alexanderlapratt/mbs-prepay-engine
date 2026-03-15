"""
cashflow_engine.py — Month-by-month MBS cash-flow projection engine.

Implements the full 8-step cash-flow loop for a mortgage pool:

  Step 1  Scheduled payment         — annuity formula
  Step 2  Scheduled interest        — balance × WAC/12
  Step 3  Scheduled principal       — payment - interest
  Step 4  CPR                       — from cpr_model.py
  Step 5  SMM from CPR              — SMM = 1 - (1-CPR)^(1/12)
  Step 6  Unscheduled principal     — SMM × (balance - scheduled_principal)
  Step 7  Total principal           — scheduled + unscheduled
  Step 8  Ending balance            — beginning_balance - total_principal

The output is a list of period dicts that feed the dashboard charts,
WAL computation, and risk engine.

Note on investor vs. gross cash flows:
  - Interest paid to the investor uses the *net* coupon (WAC minus servicing fee).
  - Scheduled payment computation uses the *gross* WAC (determines total monthly
    obligation) but investor receives net interest.
  - Principal payments are the same whether gross or net.
"""

from __future__ import annotations

import datetime
from typing import Optional

from src.mortgage_math import (
    scheduled_payment,
    monthly_interest,
    net_coupon,
    price_from_cashflows,
)
from src.cpr_model import compute_cpr
from src.utils import smm_from_cpr, clamp


# ---------------------------------------------------------------------------
# Core projection loop
# ---------------------------------------------------------------------------

def project_cashflows(
    original_balance:       float,
    wac:                    float,
    wam:                    int,
    pool_age:               int,
    current_mortgage_rate:  float,
    servicing_fee:          float     = 0.0025,
    loan_size_bucket:       str       = "medium",
    geography_bucket:       str       = "medium",
    burnout_factor:         float     = 1.0,
    turnover_factor:        float     = 1.0,
    refi_multiplier:        float     = 1.0,
    baseline_cpr:           float     = 0.05,
    max_cpr:                float     = 0.60,
    seasoning_ramp_months:  int       = 30,
    seasonality_factor:     float     = 1.0,
    start_month:            int       = 1,    # calendar month for period 1
    start_year:             int       = 2026,
) -> list[dict]:
    """
    Project monthly cash flows for a fixed-rate mortgage pool.

    Iterates month-by-month from period 1 through the pool's remaining life
    (WAM - pool_age months), applying the CPR model at each step.

    Returns a list of dicts, one per period, with keys:
        period, beginning_balance, scheduled_payment, interest,
        scheduled_principal, cpr, smm, prepayment, total_principal,
        ending_balance, total_cashflow, calendar_month, calendar_year

    Args:
        original_balance:       Starting balance for the projection ($).
                                Pass current (not original) outstanding balance
                                if the pool is already seasoned.
        wac:                    Gross WAC (decimal).
        wam:                    Remaining term in months (WAM - pool_age).
        pool_age:               Months elapsed since origination (for seasoning ramp).
        current_mortgage_rate:  Prevailing mortgage rate for refi incentive calc.
        servicing_fee:          Servicing + g-fee strip (decimal).
        loan_size_bucket:       "small" / "medium" / "large".
        geography_bucket:       "high" / "medium" / "low".
        burnout_factor:         Burnout scalar [0, 1].
        turnover_factor:        Geographic turnover multiplier.
        refi_multiplier:        Scenario refi-sensitivity scaler.
        baseline_cpr:           Housing turnover CPR floor.
        max_cpr:                CPR cap.
        seasoning_ramp_months:  PSA-style ramp period.
        seasonality_factor:     Pool-level seasonality override.
        start_month:            Calendar month of period 1 (1-12).
        start_year:             Calendar year of period 1.

    Returns:
        List of monthly cash-flow dicts.
    """
    remaining_term = wam - pool_age
    if remaining_term <= 0:
        return []

    # Compute the current outstanding balance using the closed-form formula
    # (accounts for scheduled amortization of pool_age months already elapsed)
    from src.mortgage_math import remaining_balance
    current_balance = remaining_balance(original_balance, wac, wam + pool_age, pool_age)

    net_wac        = net_coupon(wac, servicing_fee)   # investor pass-through rate
    cashflows      = []
    balance        = current_balance
    age            = pool_age  # tracks pool age for seasoning ramp

    cal_month  = start_month
    cal_year   = start_year

    for t in range(1, remaining_term + 1):
        if balance <= 1.0:   # effectively paid off
            break

        remaining_wam = remaining_term - (t - 1)

        # ----------------------------------------------------------------
        # Step 1: Scheduled payment (gross coupon drives total obligation)
        # ----------------------------------------------------------------
        sched_pmt = scheduled_payment(balance, wac, remaining_wam)

        # ----------------------------------------------------------------
        # Step 2: Scheduled interest (investor receives net coupon)
        # ----------------------------------------------------------------
        interest = monthly_interest(balance, net_wac)

        # ----------------------------------------------------------------
        # Step 3: Scheduled principal
        #         = gross scheduled payment - gross interest accrual
        # ----------------------------------------------------------------
        gross_interest  = monthly_interest(balance, wac)
        sched_prin      = sched_pmt - gross_interest
        sched_prin      = clamp(sched_prin, 0.0, balance)

        # ----------------------------------------------------------------
        # Step 4: CPR from the multi-factor model
        # ----------------------------------------------------------------
        cpr = compute_cpr(
            wac=wac,
            current_mortgage_rate=current_mortgage_rate,
            pool_age_months=age,
            calendar_month=cal_month,
            loan_size_bucket=loan_size_bucket,
            geography_bucket=geography_bucket,
            burnout_factor=burnout_factor,
            turnover_factor=turnover_factor,
            refi_multiplier=refi_multiplier,
            seasoning_ramp_months=seasoning_ramp_months,
            baseline_cpr=baseline_cpr,
            max_cpr=max_cpr,
            seasonality_factor=seasonality_factor,
        )

        # ----------------------------------------------------------------
        # Step 5: SMM (Single Monthly Mortality) from CPR
        #         SMM = 1 - (1 - CPR)^(1/12)
        # ----------------------------------------------------------------
        smm = smm_from_cpr(cpr)

        # ----------------------------------------------------------------
        # Step 6: Unscheduled (prepayment) principal
        #         Applied to balance *after* scheduled principal paydown
        # ----------------------------------------------------------------
        balance_after_sched = balance - sched_prin
        prepayment          = smm * balance_after_sched

        # ----------------------------------------------------------------
        # Step 7: Total principal
        # ----------------------------------------------------------------
        total_prin = sched_prin + prepayment
        total_prin = min(total_prin, balance)   # cannot exceed balance

        # ----------------------------------------------------------------
        # Step 8: Ending balance
        # ----------------------------------------------------------------
        ending_balance = balance - total_prin
        ending_balance = max(ending_balance, 0.0)

        total_cf = interest + total_prin

        cashflows.append({
            "period":               t,
            "beginning_balance":    round(balance, 2),
            "scheduled_payment":    round(sched_pmt, 2),
            "interest":             round(interest, 2),
            "scheduled_principal":  round(sched_prin, 2),
            "cpr":                  round(cpr, 6),
            "smm":                  round(smm, 8),
            "prepayment":           round(prepayment, 2),
            "total_principal":      round(total_prin, 2),
            "ending_balance":       round(ending_balance, 2),
            "total_cashflow":       round(total_cf, 2),
            "calendar_month":       cal_month,
            "calendar_year":        cal_year,
        })

        # Advance state
        balance   = ending_balance
        age      += 1
        cal_month += 1
        if cal_month > 12:
            cal_month = 1
            cal_year += 1

    return cashflows


# ---------------------------------------------------------------------------
# WAL calculation
# ---------------------------------------------------------------------------

def compute_wal(cashflows: list[dict], original_balance: float) -> float:
    """
    Compute the Weighted Average Life (WAL) of the pool.

    WAL = sum( t * TotalPrincipal_t ) / OriginalBalance   (in years)

    WAL is the key prepayment-adjusted duration metric for MBS.  Unlike
    standard bond duration, WAL weights only *principal* cash flows —
    not interest — giving the average time until an investor receives
    their principal back.

    A high-WAL pool (e.g. 8+ years) is more exposed to rate increases;
    a low-WAL pool is quickly returning principal and less rate-sensitive.

    Args:
        cashflows:        Output of project_cashflows().
        original_balance: Current outstanding balance (used as denominator).

    Returns:
        WAL in years (float).
    """
    if not cashflows or original_balance <= 0:
        return 0.0

    weighted_sum = sum(
        (cf["period"] / 12.0) * cf["total_principal"]
        for cf in cashflows
    )
    return weighted_sum / original_balance


# ---------------------------------------------------------------------------
# Total cash flow list extractor
# ---------------------------------------------------------------------------

def extract_total_cashflows(cashflows: list[dict]) -> list[float]:
    """
    Extract the total cash-flow (interest + principal) list from period dicts.
    Used as input to price_from_cashflows() for risk calculations.
    """
    return [cf["total_cashflow"] for cf in cashflows]
