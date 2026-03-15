"""
utils.py — Shared utility helpers for the MBS Prepayment Engine.

Covers: type coercion, date helpers, formatting, and small math primitives
used across multiple modules.
"""

from __future__ import annotations

import math
import datetime
from typing import Union


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------

def bp_to_decimal(bps: float) -> float:
    """
    Convert basis points to a decimal rate.
    E.g. 25bp -> 0.0025.

    Used throughout the codebase when applying rate shocks specified in basis
    points to decimal coupon rates.
    """
    return bps / 10_000.0


def decimal_to_bp(rate: float) -> float:
    """Convert a decimal rate to basis points.  E.g. 0.0025 -> 25."""
    return rate * 10_000.0


def pct_to_decimal(pct: float) -> float:
    """Convert a percentage (e.g. 6.5) to a decimal (0.065)."""
    return pct / 100.0


def decimal_to_pct(rate: float) -> float:
    """Convert a decimal rate (0.065) to a percentage (6.5)."""
    return rate * 100.0


def clamp(value: float, lo: float, hi: float) -> float:
    """
    Clamp *value* to the closed interval [lo, hi].
    Used to enforce CPR ceilings / floors without raising exceptions.
    """
    return max(lo, min(hi, value))


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Division that returns *default* instead of raising ZeroDivisionError.
    Useful when computing ratios on near-zero balances at pool maturity.
    """
    if denominator == 0.0 or math.isnan(denominator):
        return default
    return numerator / denominator


# ---------------------------------------------------------------------------
# Mortgage math primitives
# ---------------------------------------------------------------------------

def annualize_smm(smm: float) -> float:
    """
    Convert a Single Monthly Mortality (SMM) rate to an annualized CPR.

    CPR = 1 - (1 - SMM)^12

    This is the exact inverse of the SMM->CPR direction used in the cash-flow
    engine.  Useful for displaying annualized rates in charts.
    """
    return 1.0 - (1.0 - smm) ** 12


def smm_from_cpr(cpr: float) -> float:
    """
    Convert annualized CPR to monthly SMM.

    SMM = 1 - (1 - CPR)^(1/12)

    A pool with CPR=0.20 prepays 20% of its outstanding balance per year.
    SMM is the monthly equivalent used in cash-flow projections.
    """
    return 1.0 - (1.0 - cpr) ** (1.0 / 12.0)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_currency(value: float, decimals: int = 2) -> str:
    """Format a dollar value with commas and optional decimal places."""
    return f"${value:,.{decimals}f}"


def fmt_pct(value: float, decimals: int = 2) -> str:
    """Format a decimal rate (0.065) as a percentage string ('6.50%')."""
    return f"{value * 100:.{decimals}f}%"


def fmt_bp(value: float, decimals: int = 1) -> str:
    """Format a decimal rate (0.0025) as a basis-point string ('25.0bp')."""
    return f"{value * 10_000:.{decimals}f}bp"


def fmt_years(value: float, decimals: int = 2) -> str:
    """Format a duration / WAL value as years."""
    return f"{value:.{decimals}f}yr"


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def month_offset(base_date: datetime.date, months: int) -> datetime.date:
    """
    Add *months* to *base_date*, handling month-end roll correctly.
    Used to generate cash-flow period dates.
    """
    month = base_date.month - 1 + months
    year  = base_date.year + month // 12
    month = month % 12 + 1
    # Clamp day to last day of target month
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    day = min(base_date.day, last_day)
    return datetime.date(year, month, day)


def periods_to_dates(start_date: datetime.date, n_periods: int) -> list[datetime.date]:
    """
    Generate a list of monthly payment dates starting from *start_date*.
    Period 1 is one month after start_date.
    """
    return [month_offset(start_date, i) for i in range(1, n_periods + 1)]


# ---------------------------------------------------------------------------
# Pool validation
# ---------------------------------------------------------------------------

def validate_pool_inputs(
    original_balance: float,
    wac: float,
    wam: int,
    pool_age: int,
    current_mortgage_rate: float,
) -> list[str]:
    """
    Return a list of human-readable validation error strings (empty if valid).

    Validates ranges for the key pool inputs before running the engine so
    the dashboard can surface errors before computation begins.
    """
    errors: list[str] = []
    if original_balance <= 0:
        errors.append("Original balance must be positive.")
    if not (0.0 < wac < 0.30):
        errors.append("WAC should be between 0% and 30%.")
    if not (1 <= wam <= 360):
        errors.append("WAM must be between 1 and 360 months.")
    if not (0 <= pool_age < wam):
        errors.append("Pool age must be between 0 and WAM-1 months.")
    if not (0.0 < current_mortgage_rate < 0.30):
        errors.append("Current mortgage rate should be between 0% and 30%.")
    return errors
