"""
dashboard.py — Main Streamlit entry point for the MBS Prepayment Engine.

Run with:  streamlit run app/dashboard.py

This file handles:
  - App-wide configuration (page title, icon, layout)
  - Database initialization on first load
  - Sidebar: pool input controls (shared state across all pages via session_state)
  - Running the full scenario engine when inputs change
  - Storing results in st.session_state for consumption by each sub-page

Architecture note:
  Streamlit reruns the entire script on every user interaction.  We use
  st.session_state to cache expensive computation (the scenario engine run)
  so it only re-executes when pool inputs actually change.
"""

import sys
import os

# Ensure the project root is on the path so 'src' imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import streamlit as st
import pandas as pd

from src.db import init_db, load_pool
from src.data_loader import build_pool_params
from src.scenario_engine import run_all_scenarios
from src.config import (
    APP_TITLE,
    DEFAULT_SCENARIOS,
)
from app.components.styles import inject_css, inject_mobile_css, page_header


# ---------------------------------------------------------------------------
# Page configuration — must be the first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="MBS Prepayment Engine",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",   # collapsed by default → better on mobile
    menu_items={
        "Get Help":     "https://github.com/username/mbs-prepay-engine",
        "Report a bug": "https://github.com/username/mbs-prepay-engine/issues",
        "About":        "MBS Prepayment, Cash Flow & Hedging Engine — Yale CS/Math",
    },
)

inject_css()
inject_mobile_css()

# ---------------------------------------------------------------------------
# Database initialization (runs once per session)
# ---------------------------------------------------------------------------

@st.cache_resource
def initialize_database():
    """Initialize SQLite schema and seed data on first run."""
    try:
        init_db()
        return True
    except Exception as e:
        st.error(f"Database init failed: {e}")
        return False


initialize_database()


# ---------------------------------------------------------------------------
# Load seed pool defaults
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def get_seed_pool():
    """Load the FNMA sample pool from the database for default values."""
    return load_pool("FNMA_30Y_6PCT")


seed_pool = get_seed_pool() or {}


# ---------------------------------------------------------------------------
# Sidebar — Pool Input Controls
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Pre-populate sidebar sliders from Fannie Mae "Apply to Sidebar" button
# ---------------------------------------------------------------------------
# When the user clicks "Apply to Sidebar" on the Pool Setup page it writes
# fnma_balance / fnma_wac / fnma_wam into session_state.  We pop those values
# here (before the widgets render) and write them into the widget keys so
# Streamlit picks them up on the next rerun.  Using pop() ensures the values
# are applied exactly once — subsequent reruns use whatever the user sets.

if "fnma_balance" in st.session_state:
    _v = max(1_000_000, min(10_000_000_000, int(st.session_state.pop("fnma_balance"))))
    st.session_state["_sb_balance"] = _v

if "fnma_wac" in st.session_state:
    _v = round(float(st.session_state.pop("fnma_wac")) * 100, 3)
    _v = round(_v / 0.125) * 0.125          # snap to slider step
    st.session_state["_sb_wac_pct"] = max(2.0, min(12.0, _v))

if "fnma_wam" in st.session_state:
    _v = int(st.session_state.pop("fnma_wam"))
    _v = max(60, min(360, round(_v / 12) * 12))  # snap to multiple of 12
    st.session_state["_sb_wam"] = _v


with st.sidebar:
    st.markdown(
        "<h2 style='color:#00D4FF; margin-bottom:4px;'>📊 Pool Configuration</h2>",
        unsafe_allow_html=True,
    )
    st.caption("Adjust parameters and click **Run Analysis**")

    # Show a notice when Fannie Mae values have been loaded
    if st.session_state.get("fnma_applied"):
        _bucket = st.session_state.get("fnma_bucket", "")
        st.success(f"📂 FNMA data loaded: **{_bucket}** bucket", icon=None)

    st.divider()

    # ── Balance & Term ──────────────────────────────────────────────────────
    st.markdown("**Pool Structure**")

    original_balance = st.number_input(
        "Original Balance ($)",
        min_value=1_000_000,
        max_value=10_000_000_000,
        value=int(seed_pool.get("original_balance", 100_000_000)),
        step=1_000_000,
        format="%d",
        key="_sb_balance",
        help="Original unpaid principal balance of the pool at issuance.",
    )

    wac_pct = st.slider(
        "WAC — Gross Coupon (%)",
        min_value=2.0, max_value=12.0,
        value=float(seed_pool.get("wac", 0.065)) * 100,
        step=0.125,
        key="_sb_wac_pct",
        help="Weighted average coupon (gross, before servicing fee).",
    )
    wac = wac_pct / 100.0

    wam = st.slider(
        "WAM — Original Term (months)",
        min_value=60, max_value=360,
        value=int(seed_pool.get("wam", 360)),
        step=12,
        key="_sb_wam",
        help="Original weighted average maturity in months.",
    )

    pool_age = st.slider(
        "Pool Age (months seasoned)",
        min_value=0,
        max_value=wam - 1,
        value=min(int(seed_pool.get("pool_age", 24)), wam - 1),
        step=1,
        help="Number of months since pool origination (seasoning).",
    )

    st.divider()

    # ── Rate Environment ────────────────────────────────────────────────────
    st.markdown("**Rate Environment**")

    mortgage_rate_pct = st.slider(
        "Current Mortgage Rate (%)",
        min_value=2.0, max_value=12.0,
        value=6.50,
        step=0.125,
        help="Prevailing primary mortgage rate — drives refinancing incentive.",
    )
    current_mortgage_rate = mortgage_rate_pct / 100.0

    servicing_fee_bp = st.slider(
        "Servicing + G-Fee (bp)",
        min_value=5, max_value=100,
        value=int(seed_pool.get("servicing_fee", 0.0025) * 10000),
        step=5,
        help="Total servicing fee and agency guarantee fee strip in basis points.",
    )
    servicing_fee = servicing_fee_bp / 10000.0

    st.divider()

    # ── Prepayment Assumptions ───────────────────────────────────────────────
    st.markdown("**Prepayment Assumptions**")

    loan_size_bucket = st.selectbox(
        "Loan Size Bucket",
        options=["small", "medium", "large"],
        index=1,
        help="Small (<$150k) prepay slower; Large (>$500k) prepay faster.",
    )

    geography_bucket = st.selectbox(
        "Geography (Prepay Speed)",
        options=["low", "medium", "high"],
        index=1,
        help="High = coastal/CA; Low = rural/Midwest.",
    )

    burnout_factor = st.slider(
        "Burnout Factor",
        min_value=0.0, max_value=1.0,
        value=float(seed_pool.get("burnout_factor", 0.85)),
        step=0.05,
        help="1.0 = fresh pool; 0.0 = fully burned out (insensitive to rates).",
    )

    turnover_factor = st.slider(
        "Turnover Factor",
        min_value=0.5, max_value=2.0,
        value=float(seed_pool.get("turnover_factor", 1.0)),
        step=0.1,
        help="Housing mobility multiplier. 1.0 = national average.",
    )

    seasonality_factor = st.slider(
        "Seasonality Override",
        min_value=0.5, max_value=1.5,
        value=float(seed_pool.get("seasonality_factor", 1.0)),
        step=0.05,
        help="Pool-level seasonal adjustment. 1.0 = use calendar defaults.",
    )

    st.divider()

    run_button = st.button("🚀  Run Analysis", type="primary", use_container_width=True)


# ---------------------------------------------------------------------------
# Session state management
# ---------------------------------------------------------------------------

def _pool_params_key():
    """Build a tuple key representing current pool parameters for cache validation."""
    return (
        original_balance, wac, wam, pool_age,
        current_mortgage_rate, servicing_fee,
        loan_size_bucket, geography_bucket,
        burnout_factor, turnover_factor, seasonality_factor,
    )


# Run the engine if button pressed OR if this is the first load
should_run = run_button or "scenario_results" not in st.session_state

if should_run or st.session_state.get("_last_params") != _pool_params_key():
    try:
        pool_params = build_pool_params(
            original_balance=original_balance,
            wac=wac,
            wam=wam,
            pool_age=pool_age,
            current_mortgage_rate=current_mortgage_rate,
            servicing_fee=servicing_fee,
            loan_size_bucket=loan_size_bucket,
            geography_bucket=geography_bucket,
            burnout_factor=burnout_factor,
            turnover_factor=turnover_factor,
            seasonality_factor=seasonality_factor,
        )

        with st.spinner("Running scenario engine across 8 rate scenarios…"):
            scenario_results = run_all_scenarios(
                pool_params=pool_params,
                base_mortgage_rate=current_mortgage_rate,
            )

        st.session_state["pool_params"]       = pool_params
        st.session_state["scenario_results"]  = scenario_results
        st.session_state["_last_params"]      = _pool_params_key()

    except ValueError as e:
        st.error(f"Input validation error: {e}")
        st.stop()


# ---------------------------------------------------------------------------
# Home / Overview page
# ---------------------------------------------------------------------------

page_header(
    "MBS Prepayment, Cash Flow & Hedging Engine",
    "Fixed Income Relative Value Analytics | Fixed-Rate Agency MBS",
)

pool_params      = st.session_state.get("pool_params", {})
scenario_results = st.session_state.get("scenario_results", [])

# ── Key metrics from Base scenario ──────────────────────────────────────────
base = next((r for r in scenario_results if r["scenario_name"] == "Base"), {})

col1, col2, col3, col4, col5, col6 = st.columns(6)

from src.mortgage_math import remaining_balance as _rem_bal

current_bal = _rem_bal(
    pool_params.get("original_balance", 0),
    pool_params.get("wac", 0.065),
    pool_params.get("wam", 360) + pool_params.get("pool_age", 0),
    pool_params.get("pool_age", 0),
) if pool_params else 0

with col1:
    st.metric("Current Balance", f"${current_bal/1e6:.1f}M")
with col2:
    st.metric("WAC (Gross)", f"{(pool_params.get('wac', 0.065)*100):.3f}%")
with col3:
    st.metric("WAL (Base)", f"{base.get('wal', 0):.2f}yr")
with col4:
    st.metric("Price (Base)", f"{base.get('price', 100):.2f}")
with col5:
    st.metric("Eff. Duration", f"{base.get('eff_duration', 0):.2f}yr")
with col6:
    st.metric("Convexity", f"{base.get('convexity', 0):.3f}")

st.divider()

# ── Quick scenario table ─────────────────────────────────────────────────────
st.markdown("### Scenario Summary")
st.caption("Navigate to individual pages for detailed analysis →")

if scenario_results:
    from src.data_loader import scenario_results_to_df
    from app.components.tables import format_scenario_summary
    summary_df = scenario_results_to_df(scenario_results)
    st.dataframe(
        format_scenario_summary(summary_df),
        use_container_width=True,
        height=320,
    )

st.divider()
st.caption(
    "Built by Alexander LaPratt · Yale BS CS & Mathematics · "
    "MBS Prepayment Engine v1.0 · "
    "All data is user-supplied or model-computed — no external APIs required."
)
