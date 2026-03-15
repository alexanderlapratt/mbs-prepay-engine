"""
2_Scenario_Analysis.py — CPR scenario analysis and prepayment driver decomposition.

Shows:
  - CPR by scenario over pool life (multi-line chart)
  - SMM by scenario
  - Refi incentive vs. CPR scatter (S-curve)
  - CPR driver decomposition (stacked bar)
  - Key metric comparison table
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd

from src.data_loader import (
    multi_scenario_cpr_df,
    cpr_decomp_df,
    scenario_results_to_df,
)
from src.cpr_model import cpr_driver_decomposition
from app.components.styles import inject_css, page_header, section_header, info_box
from app.components.charts import (
    cpr_by_scenario_chart,
    refi_incentive_chart,
    cpr_decomposition_chart,
)
from app.components.tables import format_decomp_table, csv_download_button

inject_css()
page_header("Scenario Analysis", "CPR speed, SMM, and prepayment driver decomposition across 8 rate scenarios")

# ── Pull state ──────────────────────────────────────────────────────────────
scenario_results = st.session_state.get("scenario_results")
pool_params      = st.session_state.get("pool_params")

if scenario_results is None:
    info_box("Run the analysis from the **Home** page first.")
    st.stop()

# ── CPR Overview Metrics ─────────────────────────────────────────────────────
base    = next((r for r in scenario_results if r["scenario_name"] == "Base"),      {})
dn100   = next((r for r in scenario_results if r["scenario_name"] == "Down 100bp"),{})
up100   = next((r for r in scenario_results if r["scenario_name"] == "Up 100bp"),  {})

base_cpr_t1  = base.get("cashflows", [{}])[0].get("cpr", 0) * 100 if base.get("cashflows") else 0
dn100_cpr_t1 = dn100.get("cashflows", [{}])[0].get("cpr", 0) * 100 if dn100.get("cashflows") else 0
up100_cpr_t1 = up100.get("cashflows", [{}])[0].get("cpr", 0) * 100 if up100.get("cashflows") else 0

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Base CPR (Month 1)", f"{base_cpr_t1:.1f}%")
with c2:
    st.metric("Down 100bp CPR (M1)", f"{dn100_cpr_t1:.1f}%",
              delta=f"+{dn100_cpr_t1-base_cpr_t1:.1f}%")
with c3:
    st.metric("Up 100bp CPR (M1)", f"{up100_cpr_t1:.1f}%",
              delta=f"{up100_cpr_t1-base_cpr_t1:.1f}%",
              delta_color="inverse")
with c4:
    incentive_bp = (pool_params.get("wac", 0.065) - pool_params.get("current_mortgage_rate", 0.065)) * 10000
    st.metric("Refi Incentive", f"{incentive_bp:+.1f}bp",
              delta="In-the-money" if incentive_bp > 0 else "Out-of-the-money")

st.divider()

# ── CPR Charts ───────────────────────────────────────────────────────────────
section_header(
    "CPR by Scenario",
    "Annualized prepayment rate over the pool life.  "
    "Note how CPR is elevated in rally scenarios (more refinancing) and "
    "depressed in selloffs (less refinancing).  This is the core option in MBS."
)

cpr_df = multi_scenario_cpr_df(scenario_results)

tab1, tab2 = st.tabs(["📈 CPR (%)", "📉 SMM (%)"])

with tab1:
    fig = cpr_by_scenario_chart(cpr_df)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    # Re-use same chart with SMM
    import plotly.graph_objects as go
    from src.config import CHART_TEMPLATE
    from app.components.charts import SCENARIO_COLORS, _LAYOUT_DEFAULTS, GRID_COLOR
    fig_smm = go.Figure()
    for scenario, grp in cpr_df.groupby("scenario_name"):
        fig_smm.add_scatter(
            x=grp["year_frac"], y=grp["smm_pct"],
            mode="lines", name=scenario,
            line=dict(color=SCENARIO_COLORS.get(scenario, "#AAAAAA"), width=2),
        )
    fig_smm.update_layout(
        title="SMM (Single Monthly Mortality) by Scenario",
        xaxis_title="Pool Age (years)", yaxis_title="SMM (%)",
        template=CHART_TEMPLATE,
        paper_bgcolor="#0E0E1A", plot_bgcolor="#0E0E1A",
        font=dict(color="#E0E0F0"),
    )
    st.plotly_chart(fig_smm, use_container_width=True)
    st.caption("SMM = 1 − (1 − CPR)^(1/12).  SMM is applied monthly to the balance after scheduled principal.")

st.divider()

# ── Refi Incentive S-Curve ────────────────────────────────────────────────────
section_header(
    "Refinancing Incentive vs. CPR — The S-Curve",
    "The relationship between how in-the-money the pool is (WAC − market rate) "
    "and the resulting CPR.  Above ~100bp incentive, prepayments accelerate sharply; "
    "above ~200bp, they plateau (burnout / remaining pool composition effects)."
)

incentive_rows = []
for r in scenario_results:
    decomp = r.get("cpr_decomp", {})
    incentive_rows.append({
        "scenario":       r["scenario_name"],
        "incentive_bp":   decomp.get("incentive_bp", 0),
        "total_cpr_pct":  decomp.get("total_cpr", 0) * 100,
    })

fig_refi = refi_incentive_chart(incentive_rows)
st.plotly_chart(fig_refi, use_container_width=True)
st.caption(
    "**Why this matters for hedging:** A desk long MBS is effectively short this call option.  "
    "When incentive jumps from 0 to 200bp, CPR can double or triple, returning principal "
    "at the worst possible time (when rates are low and reinvestment returns are poor)."
)

st.divider()

# ── CPR Driver Decomposition ─────────────────────────────────────────────────
section_header(
    "CPR Driver Decomposition",
    "Shows how much CPR comes from refinancing vs. housing turnover in each scenario."
)

decomp_df_val = cpr_decomp_df(scenario_results)
fig_decomp = cpr_decomposition_chart(decomp_df_val)
st.plotly_chart(fig_decomp, use_container_width=True)

with st.expander("📋 Decomposition Detail Table"):
    st.dataframe(
        format_decomp_table(decomp_df_val),
        use_container_width=True,
    )

st.divider()

# ── Model Assumptions Summary ────────────────────────────────────────────────
with st.expander("⚙️  CPR Model Assumptions"):
    pp = pool_params
    st.markdown(f"""
| Parameter | Value |
|---|---|
| Burnout Factor | `{pp.get('burnout_factor', 1.0):.2f}` |
| Turnover Factor | `{pp.get('turnover_factor', 1.0):.2f}` |
| Loan Size Bucket | `{pp.get('loan_size_bucket', 'medium')}` |
| Geography Bucket | `{pp.get('geography_bucket', 'medium')}` |
| Seasonality Override | `{pp.get('seasonality_factor', 1.0):.2f}` |
| Baseline CPR Floor | `{pp.get('baseline_cpr', 0.05)*100:.1f}%` |
| CPR Cap | `{pp.get('max_cpr', 0.60)*100:.0f}%` |
""")

csv_download_button(decomp_df_val, "cpr_decomposition.csv", "Export Decomposition")
