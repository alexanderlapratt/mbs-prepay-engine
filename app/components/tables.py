"""
tables.py — DataFrame formatting helpers for Streamlit display tables.

Wraps pandas DataFrames with consistent number formatting for display
in st.dataframe() or st.table() calls.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def format_scenario_summary(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """
    Apply display formatting to the scenario summary DataFrame.

    Highlights the Base scenario row and applies color gradients to key
    risk metrics for quick visual scanning.
    """
    def highlight_base(row):
        color = "#00D4FF22" if row["Scenario"] == "Base" else ""
        return [f"background-color: {color}"] * len(row)

    styler = (
        df.style
        .apply(highlight_base, axis=1)
        .format({
            "Rate Shift (bp)":   "{:+.0f}",
            "Mortgage Rate (%)": "{:.3f}%",
            "WAL (yr)":          "{:.2f}",
            "Price (% par)":     "{:.3f}",
            "Eff. Duration":     "{:.3f}",
            "Convexity":         "{:.4f}",
            "DV01 ($)":          "${:,.0f}",
            "Hedge Units":       "{:.1f}",
        })
        .background_gradient(subset=["Eff. Duration"], cmap="Blues")
        .background_gradient(subset=["Price (% par)"],  cmap="RdYlGn")
    )
    return styler


def format_cashflow_table(df: pd.DataFrame, n_rows: int = 24) -> pd.io.formats.style.Styler:
    """
    Format the first *n_rows* of a cash-flow DataFrame for display.
    """
    cols = ["period", "beginning_balance", "interest", "scheduled_principal",
            "prepayment", "total_principal", "ending_balance", "cpr"]
    display_df = df[cols].head(n_rows).copy()
    display_df.columns = [
        "Period", "Beg. Balance", "Interest", "Sched. Principal",
        "Prepayment", "Total Principal", "End Balance", "CPR"
    ]
    styler = display_df.style.format({
        "Beg. Balance":      "${:,.0f}",
        "Interest":          "${:,.0f}",
        "Sched. Principal":  "${:,.0f}",
        "Prepayment":        "${:,.0f}",
        "Total Principal":   "${:,.0f}",
        "End Balance":       "${:,.0f}",
        "CPR":               "{:.2%}",
    })
    return styler


def format_amortization_table(df: pd.DataFrame, n_rows: int = 12) -> pd.io.formats.style.Styler:
    """Format the amortization schedule for Page 1 display."""
    display = df.head(n_rows).copy()
    styler = display.style.format({
        "beginning_balance":    "${:,.0f}",
        "scheduled_payment":    "${:,.0f}",
        "interest":             "${:,.0f}",
        "scheduled_principal":  "${:,.0f}",
        "ending_balance":       "${:,.0f}",
    })
    return styler


def format_risk_table(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Format the risk results table for Page 4."""
    fmt = {
        "wal":          "{:.2f}yr",
        "price":        "{:.3f}",
        "eff_duration": "{:.3f}",
        "convexity":    "{:.4f}",
        "dv01":         "${:,.0f}",
        "hedge_units":  "{:.1f}",
    }
    # Only format columns that exist
    fmt = {k: v for k, v in fmt.items() if k in df.columns}
    return df.style.format(fmt)


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
