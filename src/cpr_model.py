"""
cpr_model.py — Rule-based CPR (Conditional Prepayment Rate) model.

CPR represents the annualized fraction of a pool's outstanding principal that
prepays in a given month.  It is the single most important driver of MBS
price volatility and negative convexity.

This module implements a stylized multi-factor CPR model with the following
components:

  1. Refinancing incentive  — borrowers refinance when market rates are below
                              their current coupon by a meaningful amount.
  2. Seasoning ramp         — new loans prepay slowly; seasoning ramps up
                              to full speed over ~30 months (PSA convention).
  3. Burnout                — pools that have already experienced fast
                              prepayments are left with borrowers who are
                              less likely to refinance (self-selection).
  4. Turnover (baseline)    — even with no refinancing incentive, homeowners
                              sell and move (housing turnover CPR floor).
  5. Seasonality            — spring/summer housing market is more active.
  6. Loan balance multiplier — larger loans are more sensitive to rate moves.
  7. Geography multiplier   — coastal markets prepay faster.

In a real production environment (e.g. on Garda's MBS desk), CPR models
are calibrated empirically to historical agency remittance data and often
purchased from third-party vendors (Andrew Davidson & Co., Intex, etc.).
"""

from __future__ import annotations

import math
from src.config import (
    REFI_SENSITIVITY,
    PSA_RAMP_MONTHS,
    BASELINE_CPR,
    MAX_CPR,
    LOAN_SIZE_MULTIPLIERS,
    GEOGRAPHY_MULTIPLIERS,
    SEASONALITY_MULTIPLIERS,
)
from src.utils import clamp


# ---------------------------------------------------------------------------
# Component 1: Refinancing incentive
# ---------------------------------------------------------------------------

def refi_incentive_cpr(
    wac: float,
    current_mortgage_rate: float,
    refi_multiplier: float = 1.0,
    sensitivity: float = REFI_SENSITIVITY,
) -> float:
    """
    Estimate the CPR contribution from refinancing activity.

    Refinancing is profitable when the current market mortgage rate is
    meaningfully below the pool's WAC (i.e. the pool is "in-the-money").
    We model this as a logistic S-curve:

        refi_CPR = max_refi / (1 + exp(-k * incentive))

    where incentive = WAC - current_mortgage_rate (in decimal).

    The S-curve is realistic because:
      - Below ~0bp incentive: almost no refinancing (rate locks, closing costs)
      - At ~100bp incentive:  strong refinancing wave
      - Above ~200bp:         saturation (burnout sets in)

    Args:
        wac:                  Pool gross WAC (decimal).
        current_mortgage_rate: Prevailing primary mortgage rate (decimal).
        refi_multiplier:      Scenario-level scaler (e.g. 1.4 for "Down 100bp").
        sensitivity:          Logistic curve steepness (default from config).

    Returns:
        Annualized CPR contribution from refinancing (decimal, e.g. 0.15).
    """
    incentive   = wac - current_mortgage_rate   # positive = in-the-money
    # Scale sensitivity so 100bp incentive is meaningfully fast
    k           = sensitivity * 100             # work in decimal space
    max_refi    = 0.50                          # maximum refi CPR (50% cap)
    refi_cpr    = max_refi / (1.0 + math.exp(-k * incentive))
    # Subtract the midpoint (50% of max) so that at zero incentive we get ~0
    refi_cpr    = max(0.0, refi_cpr - max_refi / 2.0) * refi_multiplier
    return refi_cpr


# ---------------------------------------------------------------------------
# Component 2: Seasoning ramp (PSA-style)
# ---------------------------------------------------------------------------

def seasoning_multiplier(pool_age_months: int, ramp_months: int = PSA_RAMP_MONTHS) -> float:
    """
    Apply a linear seasoning ramp to CPR.

    New pools prepay slowly because borrowers are still in a "honeymoon"
    period — they just closed on their homes and are unlikely to immediately
    refinance or sell.  The PSA convention ramps from 0% to 100% of the
    projected CPR linearly over *ramp_months* (typically 30).

    Multiplier = min(pool_age / ramp_months, 1.0)

    Args:
        pool_age_months: Number of months since pool origination.
        ramp_months:     Number of months to reach full seasoning.

    Returns:
        Scalar in [0, 1] representing the fraction of full CPR to apply.
    """
    if ramp_months <= 0:
        return 1.0
    return min(pool_age_months / ramp_months, 1.0)


# ---------------------------------------------------------------------------
# Component 3: Burnout
# ---------------------------------------------------------------------------

def burnout_adjustment(burnout_factor: float) -> float:
    """
    Dampen CPR for pools that have already experienced significant prepayment.

    Burnout arises because rate-sensitive borrowers refinance first.  After a
    refinancing wave, the remaining pool consists of a disproportionate share
    of borrowers who are *unable* to refinance (credit impaired, underwater,
    cash-flow constrained) or simply insensitive to rate moves.  This residual
    pool prepays more slowly even if rates fall further.

    In a real model, burnout would be tracked dynamically by cumulative
    prepayment experience.  Here we use a static *burnout_factor* supplied
    as a pool attribute (1.0 = no burnout, 0.0 = fully burned out).

    Args:
        burnout_factor: Scalar in [0, 1].  User-controlled via dashboard.

    Returns:
        burnout_factor (passed through as a multiplicative adjustment).
    """
    return clamp(burnout_factor, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Component 4: Turnover baseline (housing mobility)
# ---------------------------------------------------------------------------

def turnover_cpr(turnover_factor: float = 1.0, baseline_cpr: float = BASELINE_CPR) -> float:
    """
    Compute the baseline CPR from housing turnover independent of refinancing.

    Even at zero refinancing incentive, homeowners sell and move at a rate of
    roughly 4-7% per year nationally (driven by job changes, family formation,
    divorces, estate sales).  This turnover is not rate-sensitive and provides
    a floor for CPR.

    Args:
        turnover_factor: Geographic/demographic scaler (1.0 = national average).
        baseline_cpr:    Base annualized turnover CPR (from config).

    Returns:
        Annualized turnover CPR (decimal).
    """
    return baseline_cpr * turnover_factor


# ---------------------------------------------------------------------------
# Component 5: Seasonality
# ---------------------------------------------------------------------------

def seasonality_adjustment(calendar_month: int) -> float:
    """
    Apply a calendar-month multiplier for seasonal housing market patterns.

    Spring and summer months see elevated transaction activity (more home
    sales → higher turnover CPR).  Winter months are depressed.  The
    multipliers are drawn from historical agency remittance data patterns.

    Args:
        calendar_month: Integer 1-12 representing the calendar month.

    Returns:
        Multiplicative seasonal adjustment (e.g. 1.20 for May).
    """
    return SEASONALITY_MULTIPLIERS.get(calendar_month, 1.0)


# ---------------------------------------------------------------------------
# Main CPR calculator
# ---------------------------------------------------------------------------

def compute_cpr(
    wac:                   float,
    current_mortgage_rate: float,
    pool_age_months:       int,
    calendar_month:        int       = 6,
    loan_size_bucket:      str       = "medium",
    geography_bucket:      str       = "medium",
    burnout_factor:        float     = 1.0,
    turnover_factor:       float     = 1.0,
    refi_multiplier:       float     = 1.0,
    seasoning_ramp_months: int       = PSA_RAMP_MONTHS,
    baseline_cpr:          float     = BASELINE_CPR,
    max_cpr:               float     = MAX_CPR,
    seasonality_factor:    float     = 1.0,
) -> float:
    """
    Combine all CPR model components into a single annualized CPR estimate.

    Assembly logic:
        base_cpr   = refi_incentive_cpr + turnover_cpr
        adjusted   = base_cpr * seasoning_mult * burnout_adj
                              * loan_size_mult * geography_mult * seasonality_adj
                              * pool_seasonality_factor
        final_cpr  = clamp(adjusted, baseline_cpr, max_cpr)

    The additive structure (refi + turnover) reflects the two economically
    distinct drivers: rate sensitivity and housing mobility.  Multipliers
    then scale for structural pool characteristics.

    Args:
        wac:                    Pool gross WAC (decimal).
        current_mortgage_rate:  Current primary mortgage rate (decimal).
        pool_age_months:        Months since origination (seasoning).
        calendar_month:         Month number for seasonality (1-12).
        loan_size_bucket:       "small" / "medium" / "large".
        geography_bucket:       "high" / "medium" / "low".
        burnout_factor:         Scalar [0, 1] for prior prepayment dampening.
        turnover_factor:        Geographic housing mobility scaler.
        refi_multiplier:        Scenario-level refi sensitivity scaler.
        seasoning_ramp_months:  Months to reach full seasoning.
        baseline_cpr:           Turnover floor CPR.
        max_cpr:                Absolute CPR ceiling.
        seasonality_factor:     Pool-level season adjustment override.

    Returns:
        Annualized CPR (decimal in [baseline_cpr, max_cpr]).
    """
    # Component CPRs
    refi_cpr    = refi_incentive_cpr(wac, current_mortgage_rate, refi_multiplier)
    turn_cpr    = turnover_cpr(turnover_factor, baseline_cpr)
    base_cpr    = refi_cpr + turn_cpr

    # Multiplicative adjustments
    season_mult = seasoning_multiplier(pool_age_months, seasoning_ramp_months)
    burnout_adj = burnout_adjustment(burnout_factor)
    ls_mult     = LOAN_SIZE_MULTIPLIERS.get(loan_size_bucket, 1.0)
    geo_mult    = GEOGRAPHY_MULTIPLIERS.get(geography_bucket, 1.0)
    cal_mult    = seasonality_adjustment(calendar_month)

    adjusted    = base_cpr * season_mult * burnout_adj * ls_mult * geo_mult * cal_mult * seasonality_factor

    # Always at least turnover floor (can't go below baseline even with burnout)
    floor       = turn_cpr * season_mult * ls_mult * geo_mult
    return clamp(adjusted, floor, max_cpr)


# ---------------------------------------------------------------------------
# CPR driver decomposition (for the Scenario Analysis page)
# ---------------------------------------------------------------------------

def cpr_driver_decomposition(
    wac:                   float,
    current_mortgage_rate: float,
    pool_age_months:       int,
    calendar_month:        int   = 6,
    loan_size_bucket:      str   = "medium",
    geography_bucket:      str   = "medium",
    burnout_factor:        float = 1.0,
    turnover_factor:       float = 1.0,
    refi_multiplier:       float = 1.0,
    baseline_cpr:          float = BASELINE_CPR,
    seasonality_factor:    float = 1.0,
) -> dict:
    """
    Return a dictionary showing each CPR component's contribution.

    Useful for the waterfall/decomposition chart on the Scenario Analysis
    page, letting users see exactly *why* the model predicts a given CPR.

    Returns:
        Dict with keys: refi_contribution, turnover_contribution,
        seasoning_mult, burnout_adj, geo_mult, loan_size_mult, cal_mult,
        total_cpr.
    """
    refi_cpr    = refi_incentive_cpr(wac, current_mortgage_rate, refi_multiplier)
    turn_cpr    = turnover_cpr(turnover_factor, baseline_cpr)
    season_mult = seasoning_multiplier(pool_age_months)
    burnout_adj = burnout_adjustment(burnout_factor)
    ls_mult     = LOAN_SIZE_MULTIPLIERS.get(loan_size_bucket, 1.0)
    geo_mult    = GEOGRAPHY_MULTIPLIERS.get(geography_bucket, 1.0)
    cal_mult    = seasonality_adjustment(calendar_month)
    incentive   = wac - current_mortgage_rate

    base_cpr    = refi_cpr + turn_cpr
    total_cpr   = clamp(
        base_cpr * season_mult * burnout_adj * ls_mult * geo_mult * cal_mult * seasonality_factor,
        turn_cpr * season_mult * ls_mult * geo_mult,
        MAX_CPR,
    )

    return {
        "incentive_bp":          round((incentive) * 10000, 1),
        "refi_contribution":     round(refi_cpr, 6),
        "turnover_contribution": round(turn_cpr, 6),
        "seasoning_mult":        round(season_mult, 4),
        "burnout_adj":           round(burnout_adj, 4),
        "loan_size_mult":        round(ls_mult, 4),
        "geo_mult":              round(geo_mult, 4),
        "calendar_mult":         round(cal_mult, 4),
        "total_cpr":             round(total_cpr, 6),
    }
