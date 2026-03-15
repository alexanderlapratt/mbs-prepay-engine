"""
hedge_engine.py — Hedge ratio computation and hedge analytics for MBS positions.

An MBS desk runs a variety of hedges to manage interest rate risk:

  1. Duration hedge    — match DV01 of pool with offsetting Treasury positions
  2. Convexity hedge   — use options/swaptions to address negative convexity
  3. Key-rate hedges   — hedge exposure at specific points on the yield curve

This module implements a simplified duration/DV01 hedge using 10Y Treasury
futures as the primary hedging instrument.  In practice, desks also use:
  - Interest rate swaps (to isolate spread risk from rate risk)
  - CMT/LIBOR swaptions (to buy convexity)
  - MBS TBA rolls (to manage prepayment risk directly)

The hedge ratio computed here answers the question:
  "How many 10Y Treasury futures do I need to short to be duration-neutral?"
"""

from __future__ import annotations

from src.config import TREASURY_10Y_DV01, POOL_PAR
from src.utils import safe_divide


# ---------------------------------------------------------------------------
# DV01 hedge ratio
# ---------------------------------------------------------------------------

def compute_hedge_ratio(
    pool_dv01_dollar: float,
    instrument_dv01:  float = TREASURY_10Y_DV01,
) -> float:
    """
    Compute the number of hedge instrument units needed to offset pool DV01.

    Hedge Ratio = Pool DV01 ($) / Instrument DV01 ($ per unit)

    For a long MBS position, the desk shorts Treasury futures.  A rate rise
    causes the MBS to fall in value (positive DV01) but the short futures
    gain (negative DV01 for the hedge).

    Args:
        pool_dv01_dollar:  Pool DV01 in dollars (from risk_engine.compute_risk_metrics).
        instrument_dv01:   Dollar DV01 per hedge instrument unit.

    Returns:
        Number of hedge units (positive = short the instrument).
    """
    return safe_divide(pool_dv01_dollar, instrument_dv01, default=0.0)


# ---------------------------------------------------------------------------
# Convexity hedge cost estimate (simplified)
# ---------------------------------------------------------------------------

def convexity_hedge_cost_estimate(
    convexity:        float,
    current_balance:  float,
    vol_bps_per_year: float = 100.0,
) -> float:
    """
    Estimate the dollar cost of carrying negative convexity (theta-for-gamma).

    A pool with negative convexity is short gamma: it loses value in both
    rate rallies (prepayment cap) and selloffs (extension).  Buying swaptions
    to offset this costs premium roughly proportional to:

        Cost ≈ -0.5 × Convexity × Balance × (σ × Δt)²

    where σ is rate volatility in decimal and Δt is the time horizon.

    This is a back-of-the-envelope estimate.  Real convexity hedging requires
    full option pricing (Black, LMM, etc.) and is done by structuring desks.

    Args:
        convexity:         Pool effective convexity (negative for MBS).
        current_balance:   Current outstanding balance ($).
        vol_bps_per_year:  Rate volatility assumption (basis points annualized).

    Returns:
        Estimated annual convexity drag ($ cost; negative means value loss).
    """
    sigma = vol_bps_per_year / 10_000.0   # convert to decimal
    # Annualized gamma P&L: ½ × gamma × balance × σ² (approximation)
    return 0.5 * convexity * current_balance * (sigma ** 2) / 100.0


# ---------------------------------------------------------------------------
# Scenario hedge summary
# ---------------------------------------------------------------------------

def build_hedge_summary(scenario_risks: list[dict]) -> list[dict]:
    """
    Build a multi-scenario hedge summary table.

    Takes a list of risk result dicts (one per scenario) and computes the
    hedge units, notional, and estimated P&L for each scenario.

    Args:
        scenario_risks: List of dicts from risk_engine.compute_risk_metrics(),
                        each augmented with a "scenario_name" key.

    Returns:
        List of dicts with hedge analytics per scenario.
    """
    summary = []
    for risk in scenario_risks:
        name          = risk.get("scenario_name", "Unknown")
        dv01          = risk.get("dv01", 0.0)
        hedge_units   = risk.get("hedge_units", 0.0)
        eff_dur       = risk.get("eff_duration", 0.0)
        convexity     = risk.get("convexity", 0.0)
        balance       = risk.get("current_balance", 0.0)

        conv_cost     = convexity_hedge_cost_estimate(convexity, balance)

        summary.append({
            "scenario":          name,
            "dv01_dollar":       round(dv01, 2),
            "hedge_units":       round(hedge_units, 2),
            "hedge_notional":    round(hedge_units * 100_000, 0),  # ~$100k per futures contract
            "eff_duration":      round(eff_dur, 3),
            "convexity":         round(convexity, 4),
            "convexity_cost_est": round(conv_cost, 2),
        })
    return summary
