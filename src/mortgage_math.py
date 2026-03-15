"""
mortgage_math.py — Core fixed-rate mortgage math primitives.

These functions implement the fundamental formulas for a standard fixed-rate,
fully-amortizing mortgage.  They are the building blocks consumed by the
cash-flow engine and can be tested independently with known values.

Key formulas implemented:
  1. Scheduled monthly payment (standard annuity formula)
  2. Monthly interest accrual
  3. Scheduled principal paydown
  4. Remaining balance at any future period
  5. Net coupon after servicing/g-fee strip
"""

from __future__ import annotations

import math
import numpy as np


# ---------------------------------------------------------------------------
# 1. Scheduled monthly payment
# ---------------------------------------------------------------------------

def scheduled_payment(balance: float, wac: float, wam: int) -> float:
    """
    Compute the level monthly payment for a fixed-rate mortgage.

    Uses the standard annuity (time-value-of-money) formula:

        P = B * r / (1 - (1 + r)^(-N))

    where:
        B = current outstanding principal balance
        r = monthly coupon rate = WAC / 12
        N = remaining term in months (WAM)

    In mortgage analytics, WAC is the gross coupon (before servicing strip).
    The scheduled payment is fixed for the life of the loan; as the balance
    declines, an increasing share becomes principal.

    Args:
        balance: Outstanding principal balance ($).
        wac:     Weighted average coupon (decimal, e.g. 0.065 = 6.5%).
        wam:     Remaining term in months.

    Returns:
        Monthly scheduled payment ($).
    """
    if wam <= 0:
        return 0.0
    r = wac / 12.0
    if r == 0.0:
        # Zero-coupon: pure principal amortization
        return balance / wam
    return balance * r / (1.0 - (1.0 + r) ** (-wam))


# ---------------------------------------------------------------------------
# 2. Monthly interest
# ---------------------------------------------------------------------------

def monthly_interest(balance: float, wac: float) -> float:
    """
    Compute the interest portion of a monthly payment.

    Interest_t = Balance_{t-1} * WAC / 12

    In pass-through MBS, the investor receives the *net* coupon (WAC minus
    servicing and guarantee fee).  This function computes gross interest;
    use net_coupon() to strip out the servicing fee before passing to this
    function if you want investor-level interest.

    Args:
        balance: Beginning-of-period outstanding balance ($).
        wac:     Gross WAC (decimal).

    Returns:
        Interest accrual for the month ($).
    """
    return balance * wac / 12.0


# ---------------------------------------------------------------------------
# 3. Net coupon (investor coupon after servicing/g-fee)
# ---------------------------------------------------------------------------

def net_coupon(wac: float, servicing_fee: float) -> float:
    """
    Strip the servicing / guarantee fee from the gross coupon.

    Net Coupon = WAC - Servicing Fee

    The servicing fee compensates the loan servicer and, for agency MBS,
    includes the guarantee fee paid to FNMA/FHLMC.  Typical g-fee + servicing
    is 25-50bp for agency pools.  The investor's pass-through coupon equals
    the net coupon.

    Args:
        wac:           Gross WAC (decimal).
        servicing_fee: Total servicing + g-fee strip (decimal).

    Returns:
        Investor-level net coupon (decimal).
    """
    return wac - servicing_fee


# ---------------------------------------------------------------------------
# 4. Scheduled principal
# ---------------------------------------------------------------------------

def scheduled_principal(
    balance: float, wac: float, wam: int
) -> float:
    """
    Compute the scheduled principal paydown for the current period.

    Scheduled Principal = Scheduled Payment - Monthly Interest

    This is the contractual amortization independent of any prepayments.
    At origination, scheduled principal is a small share of the payment
    (front-loaded interest); it grows over time as the balance declines.

    Args:
        balance: Beginning-of-period outstanding balance ($).
        wac:     Gross WAC (decimal).
        wam:     Remaining term in months.

    Returns:
        Scheduled principal for the month ($).
    """
    pmt      = scheduled_payment(balance, wac, wam)
    interest = monthly_interest(balance, wac)
    return pmt - interest


# ---------------------------------------------------------------------------
# 5. Remaining balance after scheduled payment (no prepayment)
# ---------------------------------------------------------------------------

def remaining_balance(
    original_balance: float,
    wac: float,
    original_wam: int,
    periods_elapsed: int,
) -> float:
    """
    Compute the outstanding balance after *periods_elapsed* scheduled payments,
    assuming zero prepayments.

    Uses the closed-form remaining balance formula:

        B_t = B_0 * [(1+r)^N - (1+r)^t] / [(1+r)^N - 1]

    where N = original WAM and t = periods elapsed.

    This is useful for generating the deterministic amortization schedule
    (PSA benchmark) and for validating the cash-flow engine's iterative
    balance calculation.

    Args:
        original_balance:  Balance at origination ($).
        wac:               Gross WAC (decimal).
        original_wam:      Original term in months.
        periods_elapsed:   Number of payments already made.

    Returns:
        Outstanding balance at period t ($).
    """
    r = wac / 12.0
    N = original_wam
    t = periods_elapsed
    if r == 0.0:
        return max(0.0, original_balance * (1.0 - t / N))
    numerator   = (1.0 + r) ** N - (1.0 + r) ** t
    denominator = (1.0 + r) ** N - 1.0
    return original_balance * numerator / denominator


# ---------------------------------------------------------------------------
# 6. Full amortization schedule (no prepayment)
# ---------------------------------------------------------------------------

def amortization_schedule(
    original_balance: float,
    wac: float,
    wam: int,
) -> list[dict]:
    """
    Generate a complete month-by-month amortization schedule assuming no
    prepayments (equivalent to the CPR = 0% case).

    Returns a list of dicts with keys:
        period, beginning_balance, scheduled_payment, interest,
        scheduled_principal, ending_balance

    This schedule is displayed on the Pool Setup page as an amortization
    preview and used internally by tests to validate the engine.

    Args:
        original_balance: Balance at origination ($).
        wac:              Gross WAC (decimal).
        wam:              Original term in months.

    Returns:
        List of period dicts from period 1 through wam.
    """
    schedule = []
    balance  = original_balance
    pmt      = scheduled_payment(balance, wac, wam)

    for t in range(1, wam + 1):
        if balance <= 0.0:
            break
        r_monthly   = wac / 12.0
        interest    = balance * r_monthly
        sched_prin  = pmt - interest
        # Final period: pay off any remaining balance due to rounding
        if t == wam:
            sched_prin = balance
        sched_prin  = min(sched_prin, balance)  # never exceed balance
        end_balance = balance - sched_prin

        schedule.append({
            "period":               t,
            "beginning_balance":    round(balance, 2),
            "scheduled_payment":    round(pmt, 2),
            "interest":             round(interest, 2),
            "scheduled_principal":  round(sched_prin, 2),
            "ending_balance":       round(max(end_balance, 0.0), 2),
        })
        balance = max(end_balance, 0.0)

    return schedule


# ---------------------------------------------------------------------------
# 7. Price from discounted cash flows
# ---------------------------------------------------------------------------

def price_from_cashflows(
    cashflows: list[float],
    discount_rate: float,
) -> float:
    """
    Compute the price (as % of original notional) of a cash-flow stream.

    Uses period-by-period discounting:

        Price = sum( CF_t / (1 + r/12)^t  for t = 1..T ) / original_balance

    This is the present-value formula underpinning effective duration and
    convexity calculations.  In a real system, cash flows would be discounted
    using the full OAS-adjusted spot curve; here we use a flat discount rate
    as a simplifying assumption.

    Args:
        cashflows:     List of total cash flows per period (interest + principal).
        discount_rate: Annual discount rate (decimal).

    Returns:
        Price as a decimal fraction of total cash flows (not % of par; the
        caller should scale by par / original_balance separately).
    """
    r_monthly = discount_rate / 12.0
    price     = 0.0
    for t, cf in enumerate(cashflows, start=1):
        price += cf / (1.0 + r_monthly) ** t
    return price
