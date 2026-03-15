"""
scenario_engine.py — Run the full cash-flow and risk engine across all scenarios.

This module orchestrates the scenario analysis:
  1. Takes a pool definition and a list of rate scenarios
  2. For each scenario: applies rate shocks, runs cash-flow projection,
     computes risk metrics, and collects results
  3. Returns structured results ready for the Streamlit dashboard

The eight standard scenarios (Base, ±50bp, ±100bp, Bull Steepener,
Bear Flattener, Vol Shock) illustrate how MBS behave differently from
bullet bonds under rate moves — specifically the asymmetric duration
extension and contraction driven by prepayment optionality.
"""

from __future__ import annotations

from src.config import DEFAULT_SCENARIOS
from src.cashflow_engine import project_cashflows, compute_wal, extract_total_cashflows
from src.risk_engine import compute_risk_metrics
from src.cpr_model import cpr_driver_decomposition
from src.utils import bp_to_decimal


# ---------------------------------------------------------------------------
# Scenario rate builder
# ---------------------------------------------------------------------------

def apply_scenario_shocks(
    base_mortgage_rate: float,
    rate_shift_bp:      float,
    slope_shift_bp:     float = 0.0,
) -> dict:
    """
    Apply parallel and slope shifts to the base rate environment.

    For the simplified flat-curve model:
      - Parallel shift moves both the mortgage rate and the discount rate.
      - Slope shift adjusts the short end vs. long end (simplified as
        a +/-50% split between 2Y and 10Y).

    In a real curve model (HJM, LIBOR Market Model), each instrument's
    rate would be mapped to the appropriate tenor.

    Args:
        base_mortgage_rate: Current prevailing mortgage rate (decimal).
        rate_shift_bp:      Parallel shift in basis points (+up, -down).
        slope_shift_bp:     2s10s slope shift (+ = steeper).

    Returns:
        Dict with shocked_mortgage_rate and shocked_discount_rate.
    """
    shift = bp_to_decimal(rate_shift_bp)
    # For 10Y-based instruments, slope shift adds half the slope change
    long_end_adj = bp_to_decimal(slope_shift_bp * 0.5)

    return {
        "shocked_mortgage_rate":  base_mortgage_rate + shift + long_end_adj,
        "shocked_discount_rate":  base_mortgage_rate + shift + long_end_adj,
    }


# ---------------------------------------------------------------------------
# Main scenario runner
# ---------------------------------------------------------------------------

def run_all_scenarios(
    pool_params:         dict,
    base_mortgage_rate:  float,
    scenarios:           list[dict] | None = None,
) -> list[dict]:
    """
    Run cash-flow projections and risk metrics for all scenarios.

    For each scenario:
      1. Apply rate shocks to get shocked mortgage rate / discount rate.
      2. Determine the CPR refi_multiplier (from scenario definitions).
      3. Project cash flows under the shocked rate environment.
      4. Compute risk metrics (price, duration, convexity, DV01, hedge).
      5. Collect CPR driver decomposition for the scenario analysis page.

    Args:
        pool_params:        Pool attribute dict (original_balance, wac, wam, etc.)
        base_mortgage_rate: Current prevailing mortgage rate (decimal).
        scenarios:          List of scenario dicts (from config.DEFAULT_SCENARIOS
                            if None).  Each must have keys: name, rate_shift_bp,
                            slope_shift_bp, vol_shift.

    Returns:
        List of scenario result dicts, each containing:
            scenario_name, rate_shift_bp, shocked_mortgage_rate,
            cashflows, wal, price, eff_duration, convexity, dv01, hedge_units,
            cpr_decomp (list of per-period CPR driver breakdowns)
    """
    if scenarios is None:
        scenarios = DEFAULT_SCENARIOS

    results = []

    for scenario in scenarios:
        name           = scenario["name"]
        rate_shift_bp  = scenario["rate_shift_bp"]
        slope_shift_bp = scenario.get("slope_shift_bp", 0.0)
        vol_shift      = scenario.get("vol_shift", 0.0)

        # Scenario-specific CPR refi multiplier
        # Vol shock doesn't change rates but widens OAS proxy
        refi_multiplier = _scenario_refi_multiplier(rate_shift_bp, slope_shift_bp, vol_shift)

        # Apply rate shocks
        shocked = apply_scenario_shocks(base_mortgage_rate, rate_shift_bp, slope_shift_bp)
        s_rate  = shocked["shocked_mortgage_rate"]
        s_disc  = shocked["shocked_discount_rate"]

        # Full risk calculation (includes cash-flow projection internally)
        risk = compute_risk_metrics(
            pool_params=pool_params,
            base_mortgage_rate=s_rate,
            base_discount_rate=s_disc,
            refi_multiplier=refi_multiplier,
        )

        # CPR driver decomposition at pool_age (period 0 snapshot)
        decomp = cpr_driver_decomposition(
            wac=pool_params["wac"],
            current_mortgage_rate=s_rate,
            pool_age_months=pool_params["pool_age"],
            loan_size_bucket=pool_params.get("loan_size_bucket", "medium"),
            geography_bucket=pool_params.get("geography_bucket", "medium"),
            burnout_factor=pool_params.get("burnout_factor", 1.0),
            turnover_factor=pool_params.get("turnover_factor", 1.0),
            refi_multiplier=refi_multiplier,
            baseline_cpr=pool_params.get("baseline_cpr", 0.05),
            seasonality_factor=pool_params.get("seasonality_factor", 1.0),
        )

        results.append({
            "scenario_name":          name,
            "rate_shift_bp":          rate_shift_bp,
            "slope_shift_bp":         slope_shift_bp,
            "vol_shift":              vol_shift,
            "shocked_mortgage_rate":  round(s_rate, 6),
            "refi_multiplier":        refi_multiplier,
            "cashflows":              risk["cashflows_base"],
            "wal":                    risk["wal"],
            "price":                  risk["price"],
            "eff_duration":           risk["eff_duration"],
            "convexity":              risk["convexity"],
            "dv01":                   risk["dv01"],
            "hedge_units":            risk["hedge_units"],
            "current_balance":        risk["current_balance"],
            "price_up":               risk["price_up"],
            "price_down":             risk["price_down"],
            "cpr_decomp":             decomp,
        })

    return results


# ---------------------------------------------------------------------------
# Helper: scenario CPR refi multiplier mapping
# ---------------------------------------------------------------------------

def _scenario_refi_multiplier(
    rate_shift_bp:  float,
    slope_shift_bp: float,
    vol_shift:      float,
) -> float:
    """
    Map rate scenario parameters to a CPR refi sensitivity multiplier.

    Larger rate rallies amplify the refinancing response; rate selloffs
    dampen it.  Slope moves have a smaller effect (long-end rate matters
    most for 30Y mortgages).  Vol shock dampens refi slightly (wider
    option-adjusted spread → borrowers less likely to refinance).

    Args:
        rate_shift_bp:  Parallel rate shift (basis points).
        slope_shift_bp: Slope change (basis points, +steeper).
        vol_shift:      Implied vol multiplier (0 = unchanged).

    Returns:
        Refi multiplier (float, typically 0.5 – 1.5).
    """
    # Parallel shift effect: 100bp down → +40% refi responsiveness
    parallel_adj = 1.0 + (-rate_shift_bp / 100.0) * 0.40

    # Slope effect: steeper curve (higher long rates) slightly reduces refis
    slope_adj    = 1.0 + (-slope_shift_bp / 100.0) * 0.10

    # Vol shock dampens refis (borrowers wait for clearer rate direction)
    vol_adj      = 1.0 - vol_shift * 0.10

    multiplier   = parallel_adj * slope_adj * vol_adj
    # Clamp to a reasonable range
    return round(max(0.30, min(2.00, multiplier)), 4)
