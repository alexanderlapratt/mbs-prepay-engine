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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import streamlit as st
import pandas as pd

from src.mortgage_math import amortization_schedule, remaining_balance, net_coupon
from src.utils import fmt_currency, fmt_pct, fmt_bp
from src.data_loader import load_fannie_mae_profiles
from app.components.styles import inject_css, page_header, section_header, metric_row, info_box
from app.components.charts import amortization_preview_chart, balance_decay_chart
from app.components.tables import format_amortization_table, csv_download_button

inject_css()
page_header("Pool Setup & Amortization Preview", "Static pool parameters and scheduled cash-flow mechanics")

# ── Real Fannie Mae Data Loader ───────────────────────────────────────────────
with st.expander("📂  Load Real Fannie Mae Pool Data", expanded=False):
    st.markdown(
        "**Source:** Fannie Mae Single-Family Loan Performance Data, 2024 Q1  \n"
        "Select a rate bucket below to auto-populate the sidebar controls "
        "with WAC, WAM, and a representative balance derived from real originations."
    )

    _fnma_loaded = False
    _fnma_profiles = None

    try:
        _fnma_profiles = load_fannie_mae_profiles()
        _fnma_loaded = True
    except FileNotFoundError as _e:
        st.warning(
            f"Pool profile data not found.  "
            f"Run `python -m src.ingest_fannie_mae` from the repo root to generate it.\n\n"
            f"_{_e}_"
        )

    if _fnma_loaded and _fnma_profiles is not None and not _fnma_profiles.empty:
        _bucket_options = _fnma_profiles["rate_bucket"].tolist()

        _col1, _col2 = st.columns([2, 3])
        with _col1:
            _selected_bucket = st.selectbox(
                "Rate Bucket",
                options=_bucket_options,
                index=3,           # default: 6-7% (largest 2024Q1 cohort)
                key="fnma_bucket_select",
                help="Groups loans by origination interest rate range.",
            )

        _row = _fnma_profiles[_fnma_profiles["rate_bucket"] == _selected_bucket].iloc[0]

        with _col2:
            st.markdown(f"""
| Stat | Value |
|------|-------|
| **Loans in bucket** | {_row['loan_count']:,} |
| **WAC** | {_row['wac']:.3f}% |
| **Avg Loan Size** | ${_row['avg_loan_size']:,.0f} |
| **Avg LTV** | {_row['avg_ltv']:.1f}% |
| **Avg FICO** | {_row.get('avg_fico', 'N/A')} |
| **Total Orig. Balance** | ${_row['total_balance']/1e9:.2f}B |
| **Top State** | {_row['top_state']} |
""")

        _load_col, _ = st.columns([1, 3])
        with _load_col:
            if st.button(
                "⬆️  Apply to Sidebar",
                key="fnma_apply_btn",
                help="Overwrites the sidebar WAC, WAM, and Balance sliders with values from this bucket.",
            ):
                # Represent the pool as a $100M slice for comparability
                _representative_balance = 100_000_000.0

                st.session_state["fnma_wac"]     = float(_row["wac"])
                st.session_state["fnma_wam"]     = int(_row["wam"])
                st.session_state["fnma_balance"]  = _representative_balance
                st.session_state["fnma_bucket"]   = _selected_bucket
                st.session_state["fnma_applied"]  = True
                st.success(
                    f"✅  Loaded **{_selected_bucket}** pool: "
                    f"WAC={_row['wac']:.3f}%, WAM={int(_row['wam'])}mo, "
                    f"Balance=$100M (representative).  "
                    f"Return to the **Home** page sidebar and click **Run Analysis**."
                )

        if st.session_state.get("fnma_applied"):
            _b = st.session_state.get("fnma_bucket", "")
            _w = st.session_state.get("fnma_wac", 0)
            st.info(
                f"🔔  Last applied: **{_b}** bucket — WAC {_w:.3f}%.  "
                f"Go to the Home page sidebar to update the sliders and re-run."
            )

        st.caption(
            "Source: Fannie Mae Single-Family Loan Performance Data (SFLP), 2024 Q1.  "
            "Pool characteristics computed from 272,963 30-year fixed-rate originations "
            "with FICO ≥ 300, LTV > 0, and rate in [2%, 12%].  "
            "Balance shown as $100M representative pool for engine comparability."
        )

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
