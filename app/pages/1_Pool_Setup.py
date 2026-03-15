"""
1_Pool_Setup.py — Pool Summary and Amortization Preview page.

Shows:
  - Pool summary card with all static parameters
  - Amortization schedule preview (no prepayment)
  - Stacked bar chart: interest vs. scheduled principal over pool life
  - Balance decay chart
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd

from src.mortgage_math import amortization_schedule, remaining_balance, net_coupon
from src.utils import fmt_currency, fmt_pct, fmt_bp
from app.components.styles import inject_css, page_header, section_header, metric_row, info_box
from app.components.charts import amortization_preview_chart, balance_decay_chart
from app.components.tables import format_amortization_table, csv_download_button

inject_css()
page_header("Pool Setup & Amortization Preview", "Static pool parameters and scheduled cash-flow mechanics")

# ── Pull state from main dashboard ──────────────────────────────────────────
pool_params = st.session_state.get("pool_params")

if pool_params is None:
    info_box("Configure your pool in the sidebar on the **Home** page and click **Run Analysis**.")
    st.stop()

pp = pool_params

# ── Pool Summary Card ────────────────────────────────────────────────────────
section_header("Pool Summary")

current_bal = remaining_balance(
    pp["original_balance"],
    pp["wac"],
    pp["wam"] + pp["pool_age"],
    pp["pool_age"],
)
net_c = net_coupon(pp["wac"], pp["servicing_fee"])
refi_incentive_bp = (pp["wac"] - pp["current_mortgage_rate"]) * 10000

metric_row([
    {"label": "Original Balance",    "value": fmt_currency(pp["original_balance"], 0)},
    {"label": "Current Balance",     "value": fmt_currency(current_bal, 0),
     "delta": f"{((current_bal/pp['original_balance'])-1)*100:.1f}% of original"},
    {"label": "Gross WAC",           "value": fmt_pct(pp["wac"])},
    {"label": "Net Coupon",          "value": fmt_pct(net_c)},
    {"label": "Servicing / G-Fee",   "value": fmt_bp(pp["servicing_fee"])},
])

st.markdown("")

metric_row([
    {"label": "Original WAM",        "value": f"{pp['wam']} mo ({pp['wam']/12:.1f}yr)"},
    {"label": "Pool Age",            "value": f"{pp['pool_age']} months"},
    {"label": "Remaining Term",      "value": f"{pp['wam']-pp['pool_age']} mo"},
    {"label": "Refi Incentive",
     "value": f"{refi_incentive_bp:+.1f}bp",
     "delta": "In-the-money" if refi_incentive_bp > 0 else "Out-of-the-money",
     "delta_color": "normal" if refi_incentive_bp > 0 else "inverse"},
    {"label": "Current Mkt Rate",    "value": fmt_pct(pp["current_mortgage_rate"])},
])

st.divider()

# ── Pool Attributes ──────────────────────────────────────────────────────────
section_header("Pool Attributes")

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(f"**Loan Size Bucket:** `{pp['loan_size_bucket']}`")
    st.markdown(f"**Geography Bucket:** `{pp['geography_bucket']}`")
with c2:
    st.markdown(f"**Burnout Factor:** `{pp['burnout_factor']:.2f}`")
    st.markdown(f"**Turnover Factor:** `{pp['turnover_factor']:.2f}`")
with c3:
    st.markdown(f"**Seasonality Override:** `{pp['seasonality_factor']:.2f}`")
    st.markdown(f"**Baseline CPR Floor:** `{pp.get('baseline_cpr', 0.05)*100:.1f}%`")

st.divider()

# ── Amortization Schedule ────────────────────────────────────────────────────
section_header(
    "Amortization Schedule (No Prepayment)",
    "Shows scheduled interest + principal assuming CPR = 0%.  "
    "Compare to the actual projected cash flows on Page 3."
)

remaining_wam = pp["wam"] - pp["pool_age"]
sched = amortization_schedule(current_bal, pp["wac"], remaining_wam)
sched_df = pd.DataFrame(sched)

tab1, tab2, tab3 = st.tabs(["📊 Payment Chart", "💧 Balance Decay", "📋 Schedule Table"])

with tab1:
    fig = amortization_preview_chart(sched_df)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Early periods are interest-heavy (top of bar is small).  "
        "As the balance amortizes, the scheduled principal share grows — "
        "this is the fundamental amortizing-bond mechanic that makes MBS different "
        "from bullet bonds (which return 100% of principal at maturity)."
    )

with tab2:
    fig2 = balance_decay_chart(sched_df)
    st.plotly_chart(fig2, use_container_width=True)
    st.caption(
        "Balance declines slowly at first (payments are mostly interest) "
        "and accelerates at the end.  When prepayments are added (Page 3), "
        "the balance declines much faster, especially in rate rally scenarios."
    )

with tab3:
    st.markdown("**First 24 periods:**")
    st.dataframe(format_amortization_table(sched_df, n_rows=24), use_container_width=True)
    csv_download_button(sched_df, "amortization_schedule.csv", "Download Full Schedule")

st.divider()

# ── Key Formula Recap ────────────────────────────────────────────────────────
with st.expander("📐  Mortgage Math Formulas"):
    st.markdown("""
**Scheduled Monthly Payment:**
```
P = B × r / (1 - (1 + r)^-N)
```
where B = balance, r = WAC/12 (monthly rate), N = WAM remaining

**Monthly Interest:**
```
Interest_t = Balance_{t-1} × NetWAC / 12
```

**Scheduled Principal:**
```
SchedPrin_t = GrossPayment_t − GrossInterest_t
```

**Net Coupon (investor):**
```
Net WAC = Gross WAC − Servicing Fee − G-Fee
```
""")
