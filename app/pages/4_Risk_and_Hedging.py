"""
4_Risk_and_Hedging.py — MBS risk metrics and Treasury hedge ratios.

Shows:
  - Price by scenario
  - WAL by scenario
  - Effective duration and convexity (dual axis)
  - DV01 and hedge units table
  - Convexity watch panel
  - Scenario risk summary table (exportable)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd

from src.data_loader import scenario_results_to_df, risk_metrics_for_chart
from src.hedge_engine import build_hedge_summary
from app.components.styles import (
    inject_css, page_header, section_header, info_box,
    metric_row, warning_box, colored_badge,
)
from app.components.charts import (
    price_by_scenario_chart,
    wal_by_scenario_chart,
    duration_convexity_chart,
    hedge_units_chart,
)
from app.components.tables import format_scenario_summary, csv_download_button

inject_css()
page_header("Risk & Hedging", "Price, WAL, effective duration, convexity, and DV01-based hedge ratios")

# ── Pull state ──────────────────────────────────────────────────────────────
scenario_results = st.session_state.get("scenario_results")
pool_params      = st.session_state.get("pool_params")

if scenario_results is None:
    info_box("Run the analysis from the **Home** page first.")
    st.stop()

base = next((r for r in scenario_results if r["scenario_name"] == "Base"), {})

# ── Key risk metrics ─────────────────────────────────────────────────────────
price_base = base.get("price", 100.0)
dur_base   = base.get("eff_duration", 0.0)
conv_base  = base.get("convexity", 0.0)
wal_base   = base.get("wal", 0.0)
dv01_base  = base.get("dv01", 0.0)
hedge_base = base.get("hedge_units", 0.0)

neg_convexity = conv_base < 0

st.markdown(
    f"**Convexity Status:** {colored_badge('NEGATIVE CONVEXITY ⚠️', '#FF4444') if neg_convexity else colored_badge('Positive Convexity', '#00FF88')}",
    unsafe_allow_html=True,
)
st.markdown("")

metric_row([
    {"label": "Price (Base)",        "value": f"{price_base:.3f}"},
    {"label": "WAL (Base)",          "value": f"{wal_base:.2f}yr"},
    {"label": "Eff. Duration",       "value": f"{dur_base:.3f}yr"},
    {"label": "Convexity",           "value": f"{conv_base:.4f}",
     "delta": "Negative" if neg_convexity else "Positive",
     "delta_color": "inverse" if neg_convexity else "normal"},
    {"label": "DV01",                "value": f"${dv01_base:,.0f}"},
    {"label": "Hedge Units (10Y)",   "value": f"{hedge_base:.1f}"},
])

if neg_convexity:
    warning_box(
        "This pool exhibits negative convexity.  In a rate rally, prepayments accelerate "
        "and cap price appreciation.  In a selloff, prepayments slow and extend duration.  "
        "Both scenarios underperform a comparable bullet bond."
    )

st.divider()

risk_df = risk_metrics_for_chart(scenario_results)

# ── Price by Scenario ─────────────────────────────────────────────────────────
section_header(
    "Price by Scenario",
    "A bullet bond with the same duration would show symmetric price moves around par.  "
    "MBS shows asymmetric behavior: price capped in rallies (prepayments return par), "
    "and larger losses in selloffs (extension risk)."
)
fig_price = price_by_scenario_chart(risk_df)
st.plotly_chart(fig_price, use_container_width=True)

st.divider()

# ── WAL by Scenario ───────────────────────────────────────────────────────────
section_header(
    "Weighted Average Life by Scenario",
    "WAL is the primary duration metric for MBS.  It shortens in rallies and "
    "extends in selloffs — the classic MBS extension/contraction dynamic."
)
fig_wal = wal_by_scenario_chart(risk_df)
st.plotly_chart(fig_wal, use_container_width=True)

st.divider()

# ── Duration & Convexity ──────────────────────────────────────────────────────
section_header(
    "Effective Duration & Convexity",
    "Effective duration accounts for prepayment optionality; it cannot be computed "
    "with a closed-form formula (unlike bullet bonds) — it requires full cash-flow "
    "re-projection across rate shocks (finite difference method)."
)
fig_dur = duration_convexity_chart(risk_df)
st.plotly_chart(fig_dur, use_container_width=True)

with st.expander("📐 Duration & Convexity Formulas"):
    st.markdown("""
**Effective Duration (bump-and-reprice):**
```
Eff. Duration = (Price_down − Price_up) / (2 × Price_base × Δr)
```

**Effective Convexity:**
```
Convexity = (Price_down + Price_up − 2 × Price_base) / (Price_base × Δr²)
```

**DV01 ($ per 1bp):**
```
DV01 = Price_base × Eff. Duration / 10,000 × Face Value
```

where Δr = 25bp rate shock and prices are re-computed via full cash-flow projection.

**Negative convexity** occurs when `Convexity < 0`, i.e. the pool loses more in
selloffs than it gains in rallies of equal magnitude.
""")

st.divider()

# ── Hedge Units ───────────────────────────────────────────────────────────────
section_header(
    "10Y Treasury Futures Hedge Units",
    "Number of 10Y futures contracts needed to neutralize DV01.  "
    "Negative sign = short the futures.  As WAL extends (selloff), more contracts needed."
)
fig_hedge = hedge_units_chart(risk_df)
st.plotly_chart(fig_hedge, use_container_width=True)

st.divider()

# ── Full Risk Table ───────────────────────────────────────────────────────────
section_header("Full Scenario Risk Table")
summary_df = scenario_results_to_df(scenario_results)
st.dataframe(format_scenario_summary(summary_df), use_container_width=True, height=350)
csv_download_button(summary_df, "risk_summary.csv", "Export Risk Summary")

st.divider()

# ── Hedge Summary ─────────────────────────────────────────────────────────────
section_header("Hedge Detail Panel")

hedge_rows = []
for r in scenario_results:
    r_copy = dict(r)
    r_copy["scenario_name"] = r["scenario_name"]
    hedge_rows.append(r_copy)

hedge_summary = build_hedge_summary(hedge_rows)
hedge_df = pd.DataFrame(hedge_summary)
st.dataframe(
    hedge_df.style.format({
        "dv01_dollar":         "${:,.0f}",
        "hedge_units":         "{:.1f}",
        "hedge_notional":      "${:,.0f}",
        "eff_duration":        "{:.3f}",
        "convexity":           "{:.4f}",
        "convexity_cost_est":  "${:,.0f}",
    }),
    use_container_width=True,
)
st.caption(
    "**Convexity Cost Estimate** is a rough approximation of annual gamma drag "
    "(½ × Γ × Balance × σ²) at 100bp annualized vol.  Real convexity hedging "
    "uses swaptions priced via Black-76 or an LMM framework."
)
