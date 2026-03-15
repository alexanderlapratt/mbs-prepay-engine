"""
data_loader.py — Pool parameter assembly and scenario data preparation.

Bridges the Streamlit UI (raw slider/dropdown values) and the analytics
engine (typed pool_params dicts).  Also contains helpers for building
pandas DataFrames from engine output, which feed the Plotly charts.

No external API calls are made here.  All data is either user-provided
through the Streamlit interface or computed by the engine.
"""

from __future__ import annotations

import datetime
import pandas as pd
import numpy as np

from src.config import DEFAULT_SCENARIOS
from src.utils import validate_pool_inputs


# ---------------------------------------------------------------------------
# Pool params dict builder
# ---------------------------------------------------------------------------

def build_pool_params(
    original_balance:      float,
    wac:                   float,
    wam:                   int,
    pool_age:              int,
    current_mortgage_rate: float,
    servicing_fee:         float  = 0.0025,
    loan_size_bucket:      str    = "medium",
    geography_bucket:      str    = "medium",
    burnout_factor:        float  = 1.0,
    turnover_factor:       float  = 1.0,
    seasonality_factor:    float  = 1.0,
    baseline_cpr:          float  = 0.05,
    max_cpr:               float  = 0.60,
    pool_id:               str    = "USER_POOL",
    pool_name:             str    = "User Defined Pool",
) -> dict:
    """
    Construct the pool_params dict consumed by the scenario and risk engines.

    Validates inputs and raises ValueError if any are out of range.

    Args:
        See field names — all correspond to pool_static table columns.

    Returns:
        Dict of validated pool parameters.
    """
    errors = validate_pool_inputs(
        original_balance, wac, wam, pool_age, current_mortgage_rate
    )
    if errors:
        raise ValueError("; ".join(errors))

    return {
        "pool_id":               pool_id,
        "pool_name":             pool_name,
        "original_balance":      original_balance,
        "wac":                   wac,
        "wam":                   wam,
        "pool_age":              pool_age,
        "current_mortgage_rate": current_mortgage_rate,
        "servicing_fee":         servicing_fee,
        "loan_size_bucket":      loan_size_bucket,
        "geography_bucket":      geography_bucket,
        "burnout_factor":        burnout_factor,
        "turnover_factor":       turnover_factor,
        "seasonality_factor":    seasonality_factor,
        "baseline_cpr":          baseline_cpr,
        "max_cpr":               max_cpr,
    }


# ---------------------------------------------------------------------------
# DataFrames from scenario results
# ---------------------------------------------------------------------------

def scenario_results_to_df(scenario_results: list[dict]) -> pd.DataFrame:
    """
    Convert the list of scenario result dicts to a summary DataFrame.

    One row per scenario.  Used to build the scenario comparison table on
    the Risk and Hedging page.
    """
    rows = []
    for r in scenario_results:
        rows.append({
            "Scenario":          r["scenario_name"],
            "Rate Shift (bp)":   r["rate_shift_bp"],
            "Mortgage Rate (%)": round(r["shocked_mortgage_rate"] * 100, 3),
            "WAL (yr)":          r["wal"],
            "Price (% par)":     r["price"],
            "Eff. Duration":     r["eff_duration"],
            "Convexity":         r["convexity"],
            "DV01 ($)":          r["dv01"],
            "Hedge Units":       r["hedge_units"],
        })
    return pd.DataFrame(rows)


def cashflows_to_df(cashflows: list[dict]) -> pd.DataFrame:
    """
    Convert cash-flow list (from project_cashflows) to a pandas DataFrame.

    Adds a 'year_frac' column for use as the x-axis in time-series charts.
    """
    if not cashflows:
        return pd.DataFrame()
    df = pd.DataFrame(cashflows)
    df["year_frac"] = df["period"] / 12.0
    return df


def multi_scenario_cpr_df(scenario_results: list[dict]) -> pd.DataFrame:
    """
    Build a long-format DataFrame of CPR by period across all scenarios.

    Columns: scenario_name, period, cpr_pct, smm_pct, year_frac
    Used for the CPR by Scenario chart on the Scenario Analysis page.
    """
    rows = []
    for result in scenario_results:
        for cf in result.get("cashflows", []):
            rows.append({
                "scenario_name": result["scenario_name"],
                "period":        cf["period"],
                "cpr_pct":       cf["cpr"] * 100.0,
                "smm_pct":       cf["smm"] * 100.0,
                "year_frac":     cf["period"] / 12.0,
            })
    return pd.DataFrame(rows)


def multi_scenario_balance_df(scenario_results: list[dict]) -> pd.DataFrame:
    """
    Build a long-format DataFrame of remaining balance by period across scenarios.

    Used for the remaining balance chart on the Cash Flow Waterfall page.
    """
    rows = []
    for result in scenario_results:
        for cf in result.get("cashflows", []):
            rows.append({
                "scenario_name":   result["scenario_name"],
                "period":          cf["period"],
                "year_frac":       cf["period"] / 12.0,
                "ending_balance":  cf["ending_balance"],
                "ending_balance_mm": cf["ending_balance"] / 1_000_000,
            })
    return pd.DataFrame(rows)


def risk_metrics_for_chart(scenario_results: list[dict]) -> pd.DataFrame:
    """
    Build a scenario comparison DataFrame for the risk charts (price, duration, etc.).

    Used for bar charts on the Risk and Hedging page.
    """
    rows = []
    for r in scenario_results:
        rows.append({
            "scenario":      r["scenario_name"],
            "rate_shift_bp": r["rate_shift_bp"],
            "price":         r["price"],
            "wal":           r["wal"],
            "eff_duration":  r["eff_duration"],
            "convexity":     r["convexity"],
            "dv01":          r["dv01"],
            "hedge_units":   r["hedge_units"],
        })
    df = pd.DataFrame(rows)
    # Order by rate shift for sensible chart ordering
    df = df.sort_values("rate_shift_bp").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Fannie Mae real-data loader
# ---------------------------------------------------------------------------

def load_fannie_mae_profiles(
    profiles_path: str | None = None,
) -> pd.DataFrame:
    """
    Load the pre-processed Fannie Mae pool profiles CSV.

    The CSV is produced by ``src/ingest_fannie_mae.py`` and stored at
    ``data/processed/fannie_mae_pool_profiles.csv`` relative to the repo root.

    Returns a DataFrame with one row per rate bucket and columns:
        rate_bucket, wac, wam, avg_ltv, avg_cltv, avg_dti, avg_fico,
        avg_loan_size, total_balance, loan_count, top_state

    Raises FileNotFoundError with a helpful message if the file hasn't been
    generated yet, so the UI can show a clear instruction rather than crashing.
    """
    import os
    from pathlib import Path

    if profiles_path is None:
        repo_root = Path(__file__).resolve().parent.parent
        profiles_path = repo_root / "data" / "processed" / "fannie_mae_pool_profiles.csv"

    profiles_path = Path(profiles_path)
    if not profiles_path.exists():
        raise FileNotFoundError(
            f"Fannie Mae profile data not found at {profiles_path}.\n"
            "Run:  python -m src.ingest_fannie_mae  to generate it."
        )

    df = pd.read_csv(profiles_path)

    # Ensure clean types
    df["wac"]           = pd.to_numeric(df["wac"],           errors="coerce")
    df["wam"]           = pd.to_numeric(df["wam"],           errors="coerce").fillna(360).astype(int)
    df["avg_ltv"]       = pd.to_numeric(df["avg_ltv"],       errors="coerce")
    df["avg_loan_size"] = pd.to_numeric(df["avg_loan_size"], errors="coerce")
    df["total_balance"] = pd.to_numeric(df["total_balance"], errors="coerce")
    df["loan_count"]    = pd.to_numeric(df["loan_count"],    errors="coerce").fillna(0).astype(int)

    return df.reset_index(drop=True)


def cpr_decomp_df(scenario_results: list[dict]) -> pd.DataFrame:
    """
    Build a DataFrame of CPR driver decomposition across scenarios.

    Used for the stacked bar decomposition chart on the Scenario Analysis page.
    """
    rows = []
    for r in scenario_results:
        decomp = r.get("cpr_decomp", {})
        rows.append({
            "scenario":              r["scenario_name"],
            "rate_shift_bp":         r["rate_shift_bp"],
            "refi_contribution_pct": decomp.get("refi_contribution", 0) * 100,
            "turnover_pct":          decomp.get("turnover_contribution", 0) * 100,
            "incentive_bp":          decomp.get("incentive_bp", 0),
            "seasoning_mult":        decomp.get("seasoning_mult", 1.0),
            "burnout_adj":           decomp.get("burnout_adj", 1.0),
            "total_cpr_pct":         decomp.get("total_cpr", 0) * 100,
        })
    return pd.DataFrame(rows)
