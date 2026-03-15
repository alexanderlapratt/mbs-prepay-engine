"""
risk_engine.py — Effective duration, convexity, and DV01 for mortgage pools.

MBS risk metrics differ from standard bond analytics because cash flows are
not fixed — they depend on interest rates through the prepayment model.  This
means we cannot use closed-form duration formulas; instead we use *finite
differences* on full cash-flow re-projections across rate shocks.

Key metrics computed:

  Price          — PV of projected cash flows as % of outstanding balance
  WAL            — Weighted Average Life (see cashflow_engine.py)
  Eff. Duration  — (Price_down - Price_up) / (2 × Price_base × Δr)
  Convexity      — (Price_up + Price_down - 2×Price_base) / (Price_base × Δr²)
  DV01           — Dollar value of 1 basis point move ($)

Negative convexity: As rates fall, faster prepayments shorten duration and
cap price appreciation (the pool gets "called away").  As rates rise, slower
prepayments extend duration and amplify price depreciation.  This is the
fundamental asymmetry that makes MBS a distinct asset class from bullets.
"""

from __future__ import annotations

from src.config import DURATION_SHOCK, TREASURY_10Y_DV01, POOL_PAR
from src.cashflow_engine import project_cashflows, extract_total_cashflows, compute_wal
from src.mortgage_math import price_from_cashflows
from src.utils import bp_to_decimal, safe_divide


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _price_at_rate(
    mortgage_rate_shocked: float,
    discount_rate_shocked: float,
    pool_params: dict,
    refi_multiplier: float = 1.0,
) -> tuple[float, list[dict]]:
    """
    Project cash flows with a shocked mortgage rate and discount at the
    shocked discount rate.  Returns (price_pct_of_par, cashflows).

    The discount rate is not the mortgage rate — it is the rate used to
    present-value the projected cash flows.  For a simple flat-curve model
    we tie both to the current market rate.  In a real OAS framework the
    discount curve would be the OAS-adjusted spot curve.

    Args:
        mortgage_rate_shocked:  New prevailing mortgage rate after shock.
        discount_rate_shocked:  New discount rate for PV computation.
        pool_params:            Dict of pool inputs from Streamlit / scenario runner.
        refi_multiplier:        Scenario CPR scaler.

    Returns:
        (price as % of par, list of cash-flow dicts)
    """
    cfs = project_cashflows(
        original_balance=pool_params["original_balance"],
        wac=pool_params["wac"],
        wam=pool_params["wam"],
        pool_age=pool_params["pool_age"],
        current_mortgage_rate=mortgage_rate_shocked,
        servicing_fee=pool_params.get("servicing_fee", 0.0025),
        loan_size_bucket=pool_params.get("loan_size_bucket", "medium"),
        geography_bucket=pool_params.get("geography_bucket", "medium"),
        burnout_factor=pool_params.get("burnout_factor", 1.0),
        turnover_factor=pool_params.get("turnover_factor", 1.0),
        refi_multiplier=refi_multiplier,
        baseline_cpr=pool_params.get("baseline_cpr", 0.05),
        max_cpr=pool_params.get("max_cpr", 0.60),
        seasonality_factor=pool_params.get("seasonality_factor", 1.0),
    )
    if not cfs:
        return (POOL_PAR, [])

    # Outstanding balance as of today (start of projection)
    from src.mortgage_math import remaining_balance
    current_bal = remaining_balance(
        pool_params["original_balance"],
        pool_params["wac"],
        pool_params["wam"] + pool_params["pool_age"],
        pool_params["pool_age"],
    )

    cf_list  = extract_total_cashflows(cfs)
    pv       = price_from_cashflows(cf_list, discount_rate_shocked)
    price    = safe_divide(pv, current_bal, default=POOL_PAR) * POOL_PAR

    return (price, cfs)


# ---------------------------------------------------------------------------
# Main risk metrics computation
# ---------------------------------------------------------------------------

def compute_risk_metrics(
    pool_params:           dict,
    base_mortgage_rate:    float,
    base_discount_rate:    float,
    rate_shock:            float   = DURATION_SHOCK,
    refi_multiplier:       float   = 1.0,
) -> dict:
    """
    Compute the full set of risk metrics for a pool under a given scenario.

    Uses the finite-difference (bump-and-reprice) approach:
        1. Price at base rate
        2. Price at rate - shock  (down scenario)
        3. Price at rate + shock  (up scenario)

    Then applies:
        Eff. Duration = (P_dn - P_up) / (2 × P_base × shock)
        Convexity     = (P_dn + P_up - 2 × P_base) / (P_base × shock²)
        DV01          = P_base × duration / 10,000  (as % of par per 1bp)
                        scaled to dollar DV01 using outstanding balance

    Args:
        pool_params:         Pool attributes dict (keys: original_balance, wac,
                             wam, pool_age, servicing_fee, etc.).
        base_mortgage_rate:  Scenario mortgage rate (already shifted).
        base_discount_rate:  Scenario discount rate.
        rate_shock:          Finite-difference step size (decimal, default 25bp).
        refi_multiplier:     Scenario CPR scaler.

    Returns:
        Dict with: price, wal, eff_duration, convexity, dv01, hedge_units,
                   cashflows_base, cashflows_up, cashflows_down.
    """
    shock = rate_shock

    # ---- Price and cash flows under three rate scenarios ----
    p_base, cfs_base = _price_at_rate(base_mortgage_rate,            base_discount_rate,            pool_params, refi_multiplier)
    p_down, cfs_down = _price_at_rate(base_mortgage_rate - shock,    base_discount_rate - shock,    pool_params, refi_multiplier)
    p_up,   cfs_up   = _price_at_rate(base_mortgage_rate + shock,    base_discount_rate + shock,    pool_params, refi_multiplier)

    # ---- WAL from base cash flows ----
    from src.mortgage_math import remaining_balance
    current_bal = remaining_balance(
        pool_params["original_balance"],
        pool_params["wac"],
        pool_params["wam"] + pool_params["pool_age"],
        pool_params["pool_age"],
    )
    wal = compute_wal(cfs_base, current_bal)

    # ---- Effective Duration (years) ----
    # Formula: EffDur = (P_dn - P_up) / (2 * P_base * dr)
    # Positive duration → price falls when rates rise.
    # MBS duration is typically shorter than same-maturity bullet because
    # prepayments accelerate when rates fall (limiting price upside).
    eff_duration = safe_divide(
        p_down - p_up,
        2.0 * p_base * shock,
        default=0.0,
    )

    # ---- Convexity ----
    # Formula: Conv = (P_dn + P_up - 2*P_base) / (P_base * dr^2)
    # MBS exhibit negative convexity: the pool "shortens" in rallies
    # and "extends" in selloffs, both hurting relative performance.
    convexity = safe_divide(
        p_down + p_up - 2.0 * p_base,
        p_base * shock ** 2,
        default=0.0,
    )

    # ---- DV01 ($) ----
    # Dollar value of 1 basis point for the pool's current outstanding balance.
    # DV01 = Price * Duration / 10,000 × face_value
    # This is what a trader uses to size a hedge.
    dv01_pct   = p_base * eff_duration / 10_000.0   # % of par per 1bp
    dv01_dollar = dv01_pct / 100.0 * current_bal     # $ absolute

    # ---- Hedge units (10Y Treasury futures proxy) ----
    # Number of 10Y Treasury futures contracts needed to neutralize DV01.
    # Negative sign: you short Treasuries to hedge a long MBS position.
    hedge_units = safe_divide(dv01_dollar, TREASURY_10Y_DV01, default=0.0)

    return {
        "price":           round(p_base, 4),
        "wal":             round(wal, 4),
        "eff_duration":    round(eff_duration, 4),
        "convexity":       round(convexity, 4),
        "dv01":            round(dv01_dollar, 2),
        "hedge_units":     round(hedge_units, 2),
        "cashflows_base":  cfs_base,
        "cashflows_up":    cfs_up,
        "cashflows_down":  cfs_down,
        "price_up":        round(p_up, 4),
        "price_down":      round(p_down, 4),
        "current_balance": round(current_bal, 2),
    }
