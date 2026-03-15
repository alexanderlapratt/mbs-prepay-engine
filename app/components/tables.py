"""
tables.py — DataFrame formatting helpers for Streamlit display tables.

Returns plain pandas DataFrames with pre-formatted string columns so
st.dataframe() works across all Streamlit versions without requiring
pandas Styler objects (which have compatibility issues in some environments).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(df: pd.DataFrame, col: str, fmt: str) -> pd.DataFrame:
    """In-place format a numeric column to a string column."""
    if col in df.columns:
        df[col] = df[col].apply(lambda x: fmt.format(x) if pd.notna(x) else "")
    return df


# ---------------------------------------------------------------------------
# Formatters — all return plain pd.DataFrame
# ---------------------------------------------------------------------------

def format_scenario_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a display-ready copy of the scenario summary DataFrame with
    pre-formatted string columns.  Plain DataFrame — no Styler.
    """
    out = df.copy()
    _fmt(out, "Rate Shift (bp)",   "{:+.0f}")
    _fmt(out, "Mortgage Rate (%)", "{:.3f}%")
    _fmt(out, "WAL (yr)",          "{:.2f}")
    _fmt(out, "Price (% par)",     "{:.3f}")
    _fmt(out, "Eff. Duration",     "{:.3f}")
    _fmt(out, "Convexity",         "{:.4f}")
    _fmt(out, "DV01 ($)",          "${:,.0f}")
    _fmt(out, "Hedge Units",       "{:.1f}")
    return out


def format_cashflow_table(df: pd.DataFrame, n_rows: int = 24) -> pd.DataFrame:
    """
    Return a display-ready copy of the first *n_rows* cash-flow periods
    with pre-formatted string columns.  Plain DataFrame — no Styler.
    """
    cols = ["period", "beginning_balance", "interest", "scheduled_principal",
            "prepayment", "total_principal", "ending_balance", "cpr"]
    out = df[cols].head(n_rows).copy()
    out.columns = [
        "Period", "Beg. Balance", "Interest", "Sched. Principal",
        "Prepayment", "Total Principal", "End Balance", "CPR",
    ]
    for col in ["Beg. Balance", "Interest", "Sched. Principal",
                "Prepayment", "Total Principal", "End Balance"]:
        _fmt(out, col, "${:,.0f}")
    out["CPR"] = out["CPR"].apply(lambda x: f"{x:.2%}" if pd.notna(x) else "")
    return out


def format_amortization_table(df: pd.DataFrame, n_rows: int = 12) -> pd.DataFrame:
    """
    Return a display-ready copy of the amortization schedule with
    pre-formatted string columns.  Plain DataFrame — no Styler.
    """
    out = df.head(n_rows).copy()
    for col in ["beginning_balance", "scheduled_payment",
                "interest", "scheduled_principal", "ending_balance"]:
        _fmt(out, col, "${:,.0f}")
    return out


def format_risk_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a display-ready copy of the risk results table with
    pre-formatted string columns.  Plain DataFrame — no Styler.
    """
    out = df.copy()
    _fmt(out, "wal",          "{:.2f}yr")
    _fmt(out, "price",        "{:.3f}")
    _fmt(out, "eff_duration", "{:.3f}")
    _fmt(out, "convexity",    "{:.4f}")
    _fmt(out, "dv01",         "${:,.0f}")
    _fmt(out, "hedge_units",  "{:.1f}")
    return out


def format_hedge_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a display-ready copy of the hedge summary table with
    pre-formatted string columns.  Plain DataFrame — no Styler.
    """
    out = df.copy()
    _fmt(out, "dv01_dollar",        "${:,.0f}")
    _fmt(out, "hedge_units",        "{:.1f}")
    _fmt(out, "hedge_notional",     "${:,.0f}")
    _fmt(out, "eff_duration",       "{:.3f}")
    _fmt(out, "convexity",          "{:.4f}")
    _fmt(out, "convexity_cost_est", "${:,.0f}")
    return out


def format_decomp_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a display-ready copy of the CPR decomposition table with
    pre-formatted string columns.  Plain DataFrame — no Styler.
    """
    out = df.copy()
    _fmt(out, "refi_contribution_pct", "{:.2f}%")
    _fmt(out, "turnover_pct",          "{:.2f}%")
    _fmt(out, "total_cpr_pct",         "{:.2f}%")
    _fmt(out, "seasoning_mult",        "{:.3f}")
    _fmt(out, "burnout_adj",           "{:.3f}")
    _fmt(out, "incentive_bp",          "{:+.1f}")
    return out


def csv_download_button(df: pd.DataFrame, filename: str, label: str = "Export CSV") -> None:
    """
    Render a Streamlit download button for a DataFrame as CSV.

    Args:
        df:       DataFrame to export.
        filename: Name of the downloaded file (e.g. "cashflows_base.csv").
        label:    Button label text.
    """
    csv = df.to_csv(index=False)
    st.download_button(
        label=f"⬇️  {label}",
        data=csv,
        file_name=filename,
        mime="text/csv",
    )
