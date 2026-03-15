"""
3_Cashflow_Waterfall.py — Monthly cash-flow waterfall visualization.

Shows:
  - Stacked area chart: interest / scheduled principal / prepayment per month
  - Remaining balance by scenario (multi-line)
  - Cumulative principal return
  - Downloadable cash-flow tables
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd

from src.data_loader import cashflows_to_df, multi_scenario_balance_df
from app.components.styles import inject_css, page_header, section_header, info_box, metric_row
from app.components.charts import (
    cashflow_waterfall_chart,
    remaining_balance_chart,
    cumulative_principal_chart,
)
from app.components.tables import format_cashflow_table, csv_download_button

inject_css()
page_header("Cash Flow Waterfall", "Monthly interest, scheduled principal, and prepayment breakdown")

# ── Pull state ──────────────────────────────────────────────────────────────
scenario_results = st.session_state.get("scenario_results")
pool_params      = st.session_state.get("pool_params")

if scenario_results is None:
    info_box("Run the analysis from the **Home** page first.")
    st.stop()

# ── Scenario selector ────────────────────────────────────────────────────────
scenario_names   = [r["scenario_name"] for r in scenario_results]
selected_scenario = st.selectbox(
    "Select Scenario for Waterfall",
    options=scenario_names,
    index=0,
    help="Choose which rate scenario to display in the cash-flow waterfall.",
)

selected = next(r for r in scenario_results if r["scenario_name"] == selected_scenario)
cf_df    = cashflows_to_df(selected["cashflows"])

st.divider()

# ── Key cash-flow metrics ────────────────────────────────────────────────────
total_interest   = cf_df["interest"].sum()
total_sched_prin = cf_df["scheduled_principal"].sum()
total_prepay     = cf_df["prepayment"].sum()
total_principal  = cf_df["total_principal"].sum()
total_cf         = cf_df["total_cashflow"].sum()
n_periods        = len(cf_df)

from src.mortgage_math import remaining_balance
current_bal = remaining_balance(
    pool_params["original_balance"],
    pool_params["wac"],
    pool_params["wam"] + pool_params["pool_age"],
    pool_params["pool_age"],
)

metric_row([
    {"label": "Total Interest",        "value": f"${total_interest/1e6:.2f}M"},
    {"label": "Sched. Principal",      "value": f"${total_sched_prin/1e6:.2f}M"},
    {"label": "Prepayment Principal",  "value": f"${total_prepay/1e6:.2f}M",
     "delta": f"{total_prepay/current_bal*100:.1f}% of balance"},
    {"label": "Total Cash Flow",       "value": f"${total_cf/1e6:.2f}M"},
    {"label": "Pool Life",             "value": f"{n_periods} mo ({n_periods/12:.1f}yr)"},
])

st.divider()

# ── Waterfall Chart ──────────────────────────────────────────────────────────
section_header(
    "Monthly Cash Flow Waterfall",
    f"Scenario: **{selected_scenario}** — Stacked by interest / scheduled principal / prepayment"
)
fig_wf = cashflow_waterfall_chart(cf_df)
st.plotly_chart(fig_wf, use_container_width=True)

st.caption(
    "The prepayment (amber) layer grows when rates are below WAC (refinancing incentive).  "
    "In the Base scenario, the prepayment component reflects a blended turnover + moderate refi speed.  "
    "Contrast with Down 100bp below — where prepayment dominates — vs. Up 100bp where it nearly disappears."
)

st.divider()

# ── Remaining Balance Comparison ─────────────────────────────────────────────
section_header(
    "Remaining Balance by Scenario",
    "Shows duration extension (slow balance paydown in selloffs) and "
    "contraction (fast paydown in rallies) — the source of negative convexity."
)

bal_df = multi_scenario_balance_df(scenario_results)
fig_bal = remaining_balance_chart(bal_df)
st.plotly_chart(fig_bal, use_container_width=True)

st.caption(
    "**Key insight — negative convexity:** In a 100bp rally, the pool returns capital quickly "
    "(short WAL, investor must reinvest at lower rates).  In a 100bp selloff, the pool extends "
    "(long WAL, investor stuck holding a below-market coupon).  This two-sided pain is negative convexity."
)

st.divider()

# ── Annual Principal ──────────────────────────────────────────────────────────
section_header("Annual Principal Return")
fig_ann = cumulative_principal_chart(cf_df)
st.plotly_chart(fig_ann, use_container_width=True)

st.divider()

# ── Cash Flow Table ───────────────────────────────────────────────────────────
section_header("Period-by-Period Cash Flow Table")

n_show = st.slider("Number of periods to display", 12, min(len(cf_df), 360), 36, step=12)
st.dataframe(format_cashflow_table(cf_df, n_rows=n_show), use_container_width=True)

csv_download_button(cf_df, f"cashflows_{selected_scenario.replace(' ', '_').lower()}.csv",
                    f"Export {selected_scenario} Cash Flows")

st.divider()

# ── Scenario Comparison Table ─────────────────────────────────────────────────
with st.expander("📋 All-Scenario Principal Summary"):
    rows = []
    for r in scenario_results:
        cfs = r.get("cashflows", [])
        if cfs:
            total_p  = sum(c["total_principal"] for c in cfs)
            total_pp = sum(c["prepayment"] for c in cfs)
            rows.append({
                "Scenario":        r["scenario_name"],
                "Total Principal": f"${total_p/1e6:.2f}M",
                "of which Prepay": f"${total_pp/1e6:.2f}M",
                "Prepay %":        f"{total_pp/max(total_p,1)*100:.1f}%",
                "Pool Life (mo)":  len(cfs),
            })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
