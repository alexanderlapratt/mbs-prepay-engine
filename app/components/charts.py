"""
charts.py — Plotly chart factory functions for the MBS dashboard.

Every chart in the app is built here.  Each function accepts prepared
pandas DataFrames and returns a Plotly Figure object that the calling
page displays with st.plotly_chart(fig, use_container_width=True).

Using a centralized chart module:
  - Ensures consistent dark-theme styling across all pages
  - Makes charts easy to unit-test independently
  - Allows quick global style updates (e.g., color palette, font size)
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from src.config import (
    CHART_TEMPLATE,
    PRIMARY_COLOR,
    SUCCESS_COLOR,
    WARNING_COLOR,
    DANGER_COLOR,
    GRID_COLOR,
)

# Consistent scenario color palette
SCENARIO_COLORS = {
    "Base":           "#00D4FF",
    "Down 50bp":      "#00FF88",
    "Down 100bp":     "#00FFCC",
    "Up 50bp":        "#FFB800",
    "Up 100bp":       "#FF6644",
    "Bull Steepener": "#AA88FF",
    "Bear Flattener": "#FF88AA",
    "Vol Shock":      "#FFDD44",
}

_LAYOUT_DEFAULTS = dict(
    template=CHART_TEMPLATE,
    paper_bgcolor="#0E0E1A",
    plot_bgcolor="#0E0E1A",
    font=dict(family="Inter, Segoe UI, sans-serif", color="#E0E0F0", size=12),
    margin=dict(l=50, r=30, t=50, b=50),
    legend=dict(
        bgcolor="#1A1A2E",
        bordercolor="#2A2A3E",
        borderwidth=1,
        font=dict(size=11),
    ),
    xaxis=dict(gridcolor=GRID_COLOR, linecolor="#2A2A3E"),
    yaxis=dict(gridcolor=GRID_COLOR, linecolor="#2A2A3E"),
)


def _base_layout(**overrides) -> dict:
    layout = dict(_LAYOUT_DEFAULTS)
    layout.update(overrides)
    return layout


# ---------------------------------------------------------------------------
# Page 1: Pool Setup
# ---------------------------------------------------------------------------

def amortization_preview_chart(df: pd.DataFrame) -> go.Figure:
    """
    Stacked bar chart: interest vs. scheduled principal over the pool life.
    Shows how the payment composition shifts from interest-heavy (early) to
    principal-heavy (late) — the fundamental amortization mechanics.
    """
    fig = go.Figure()
    fig.add_bar(
        x=df["period"], y=df["interest"] / 1e6,
        name="Interest", marker_color="#00D4FF", opacity=0.85,
    )
    fig.add_bar(
        x=df["period"], y=df["scheduled_principal"] / 1e6,
        name="Scheduled Principal", marker_color=SUCCESS_COLOR, opacity=0.85,
    )
    fig.update_layout(
        barmode="stack",
        title="Amortization Preview — Interest vs. Principal",
        xaxis_title="Period (months)",
        yaxis_title="Cash Flow ($M)",
        **_base_layout(),
    )
    return fig


def balance_decay_chart(df: pd.DataFrame) -> go.Figure:
    """Line chart of remaining balance over time (no prepayment amortization)."""
    fig = go.Figure()
    fig.add_scatter(
        x=df["period"], y=df["ending_balance"] / 1e6,
        mode="lines", name="Remaining Balance",
        line=dict(color=PRIMARY_COLOR, width=2),
        fill="tozeroy", fillcolor="rgba(0,212,255,0.07)",
    )
    fig.update_layout(
        title="Balance Decay — Scheduled Amortization",
        xaxis_title="Period (months)",
        yaxis_title="Outstanding Balance ($M)",
        **_base_layout(),
    )
    return fig


# ---------------------------------------------------------------------------
# Page 2: Scenario Analysis
# ---------------------------------------------------------------------------

def cpr_by_scenario_chart(df: pd.DataFrame) -> go.Figure:
    """
    Multi-line chart of annualized CPR (%) over time for each scenario.
    Illustrates how CPR accelerates in rally scenarios and decelerates in
    selloff scenarios — the key driver of MBS cash-flow optionality.
    """
    fig = go.Figure()
    for scenario, grp in df.groupby("scenario_name"):
        fig.add_scatter(
            x=grp["year_frac"], y=grp["cpr_pct"],
            mode="lines",
            name=scenario,
            line=dict(color=SCENARIO_COLORS.get(scenario, "#AAAAAA"), width=2),
        )
    fig.update_layout(
        title="CPR by Scenario — Prepayment Speed Over Pool Life",
        xaxis_title="Pool Age (years)",
        yaxis_title="Annualized CPR (%)",
        **_base_layout(),
    )
    return fig


def refi_incentive_chart(incentive_data: list[dict]) -> go.Figure:
    """
    Scatter chart showing refinancing incentive (WAC - market rate) vs.
    projected CPR across scenarios.  Reveals the S-curve relationship between
    incentive and prepayment speed.
    """
    df = pd.DataFrame(incentive_data)
    fig = px.scatter(
        df,
        x="incentive_bp", y="total_cpr_pct",
        color="scenario",
        text="scenario",
        size_max=12,
        color_discrete_map={s: SCENARIO_COLORS.get(s, "#AAAAAA") for s in df["scenario"].unique()},
        template=CHART_TEMPLATE,
    )
    fig.update_traces(textposition="top center", marker_size=10)
    fig.update_layout(
        title="Refi Incentive vs. CPR — The S-Curve",
        xaxis_title="Refinancing Incentive (bp) [WAC − Market Rate]",
        yaxis_title="Projected CPR (%)",
        **_base_layout(),
    )
    fig.add_vline(x=0, line_dash="dash", line_color="#FF4444",
                  annotation_text="At-the-money", annotation_position="top right")
    return fig


def cpr_decomposition_chart(df: pd.DataFrame) -> go.Figure:
    """
    Horizontal stacked bar chart decomposing CPR into its components across
    scenarios — shows how much of the CPR comes from refi vs. turnover.
    """
    fig = go.Figure()
    fig.add_bar(
        y=df["scenario"], x=df["refi_contribution_pct"],
        name="Refi Component", orientation="h",
        marker_color=PRIMARY_COLOR, opacity=0.85,
    )
    fig.add_bar(
        y=df["scenario"], x=df["turnover_pct"],
        name="Turnover Component", orientation="h",
        marker_color=SUCCESS_COLOR, opacity=0.85,
    )
    fig.update_layout(
        barmode="stack",
        title="CPR Driver Decomposition by Scenario",
        xaxis_title="CPR (%)",
        yaxis_title="Scenario",
        **_base_layout(),
    )
    return fig


# ---------------------------------------------------------------------------
# Page 3: Cash Flow Waterfall
# ---------------------------------------------------------------------------

def cashflow_waterfall_chart(df: pd.DataFrame) -> go.Figure:
    """
    Stacked area chart of monthly cash flows split by type:
      - Interest (investor net coupon)
      - Scheduled principal (contractual amortization)
      - Prepayment principal (unscheduled)

    The prepayment component grows in rally scenarios (more refi) and
    shrinks in selloffs — visually demonstrating the cash-flow optionality.
    """
    fig = go.Figure()
    fig.add_scatter(
        x=df["year_frac"], y=df["interest"] / 1e6,
        mode="lines", name="Interest",
        stackgroup="cf", line=dict(color="#00D4FF", width=0.5),
        fillcolor="rgba(0,212,255,0.33)",
    )
    fig.add_scatter(
        x=df["year_frac"], y=df["scheduled_principal"] / 1e6,
        mode="lines", name="Scheduled Principal",
        stackgroup="cf", line=dict(color=SUCCESS_COLOR, width=0.5),
        fillcolor="rgba(0,255,136,0.33)",
    )
    fig.add_scatter(
        x=df["year_frac"], y=df["prepayment"] / 1e6,
        mode="lines", name="Prepayment",
        stackgroup="cf", line=dict(color=WARNING_COLOR, width=0.5),
        fillcolor="rgba(255,184,0,0.33)",
    )
    fig.update_layout(
        title="Monthly Cash Flow Waterfall",
        xaxis_title="Pool Age (years)",
        yaxis_title="Cash Flow ($M / month)",
        **_base_layout(),
    )
    return fig


def remaining_balance_chart(df: pd.DataFrame) -> go.Figure:
    """
    Multi-scenario remaining balance chart.  In rally scenarios the balance
    declines faster (prepayment), shortening duration.  In selloffs it
    declines slowly (extension), lengthening duration = negative convexity.
    """
    fig = go.Figure()
    for scenario, grp in df.groupby("scenario_name"):
        fig.add_scatter(
            x=grp["year_frac"], y=grp["ending_balance_mm"],
            mode="lines", name=scenario,
            line=dict(color=SCENARIO_COLORS.get(scenario, "#AAAAAA"), width=2),
        )
    fig.update_layout(
        title="Remaining Balance by Scenario — Duration Extension / Contraction",
        xaxis_title="Pool Age (years)",
        yaxis_title="Remaining Balance ($M)",
        **_base_layout(),
    )
    return fig


def cumulative_principal_chart(df: pd.DataFrame) -> go.Figure:
    """Bar chart of cumulative principal return by year."""
    df2 = df.copy()
    df2["year"] = (df2["period"] / 12).astype(int) + 1
    annual = df2.groupby("year")["total_principal"].sum().reset_index()
    annual["total_principal_mm"] = annual["total_principal"] / 1e6

    fig = go.Figure()
    fig.add_bar(
        x=annual["year"], y=annual["total_principal_mm"],
        name="Total Principal", marker_color=PRIMARY_COLOR, opacity=0.85,
    )
    fig.update_layout(
        title="Annual Principal Return ($M)",
        xaxis_title="Year",
        yaxis_title="Principal ($M)",
        **_base_layout(),
    )
    return fig


# ---------------------------------------------------------------------------
# Page 4: Risk and Hedging
# ---------------------------------------------------------------------------

def price_by_scenario_chart(df: pd.DataFrame) -> go.Figure:
    """
    Bar chart of price (% of par) by scenario.  Demonstrates negative
    convexity: prices don't move symmetrically around base in a rate rally
    vs. a selloff of equal magnitude.
    """
    colors = [SCENARIO_COLORS.get(s, "#AAAAAA") for s in df["scenario"]]
    fig = go.Figure()
    fig.add_bar(
        x=df["scenario"], y=df["price"],
        marker_color=colors, opacity=0.85,
        text=[f"{v:.2f}" for v in df["price"]],
        textposition="outside",
    )
    fig.add_hline(y=100.0, line_dash="dash", line_color="#FF4444",
                  annotation_text="Par (100)", annotation_position="right")
    fig.update_layout(
        title="Price by Scenario (% of Par)",
        xaxis_title="Scenario",
        yaxis_title="Price (% par)",
        **_base_layout(),
    )
    return fig


def wal_by_scenario_chart(df: pd.DataFrame) -> go.Figure:
    """
    Bar chart of WAL by scenario.  WAL lengthens in selloffs (prepayments
    slow down) and shortens in rallies (prepayments accelerate).
    """
    colors = [SCENARIO_COLORS.get(s, "#AAAAAA") for s in df["scenario"]]
    fig = go.Figure()
    fig.add_bar(
        x=df["scenario"], y=df["wal"],
        marker_color=colors, opacity=0.85,
        text=[f"{v:.2f}yr" for v in df["wal"]],
        textposition="outside",
    )
    fig.update_layout(
        title="Weighted Average Life by Scenario",
        xaxis_title="Scenario",
        yaxis_title="WAL (years)",
        **_base_layout(),
    )
    return fig


def duration_convexity_chart(df: pd.DataFrame) -> go.Figure:
    """
    Dual-axis chart: effective duration (left) and convexity (right) by scenario.
    Negative convexity is the defining feature of MBS — this chart makes it clear.
    """
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    colors = [SCENARIO_COLORS.get(s, "#AAAAAA") for s in df["scenario"]]

    fig.add_bar(
        x=df["scenario"], y=df["eff_duration"],
        name="Eff. Duration (yr)", marker_color=PRIMARY_COLOR, opacity=0.8,
        secondary_y=False,
    )
    fig.add_scatter(
        x=df["scenario"], y=df["convexity"],
        name="Convexity", mode="lines+markers",
        line=dict(color=DANGER_COLOR, width=2),
        marker=dict(size=8, color=DANGER_COLOR),
        secondary_y=True,
    )
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.27)",
                  annotation_text="Zero Convexity", secondary_y=True)
    fig.update_yaxes(title_text="Effective Duration (years)", secondary_y=False,
                     gridcolor=GRID_COLOR)
    fig.update_yaxes(title_text="Convexity", secondary_y=True, gridcolor=GRID_COLOR)
    fig.update_layout(
        title="Effective Duration & Convexity by Scenario",
        xaxis_title="Scenario",
        **_base_layout(),
    )
    return fig


def hedge_units_chart(df: pd.DataFrame) -> go.Figure:
    """Bar chart of 10Y Treasury futures hedge units required per scenario."""
    colors = [SCENARIO_COLORS.get(s, "#AAAAAA") for s in df["scenario"]]
    fig = go.Figure()
    fig.add_bar(
        x=df["scenario"], y=df["hedge_units"],
        marker_color=colors, opacity=0.85,
        text=[f"{v:.1f}" for v in df["hedge_units"]],
        textposition="outside",
    )
    fig.update_layout(
        title="10Y Treasury Futures Hedge Units Required",
        xaxis_title="Scenario",
        yaxis_title="Contracts (short)",
        **_base_layout(),
    )
    return fig
