"""
styles.py — Shared CSS / Streamlit styling for the MBS dashboard.

Injects a dark-theme CSS stylesheet and defines helper functions for
metric cards, badges, and section headers.  All pages import from here
to ensure consistent visual style.
"""

import streamlit as st


# ---------------------------------------------------------------------------
# Global CSS injection
# ---------------------------------------------------------------------------

DARK_CSS = """
<style>
/* ── Base ── */
html, body, [data-testid="stApp"] {
    background-color: #0E0E1A;
    color: #E0E0F0;
    font-family: 'Inter', 'Segoe UI', sans-serif;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: #13131F;
    border-right: 1px solid #2A2A3E;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: #1A1A2E;
    border: 1px solid #2A2A3E;
    border-radius: 8px;
    padding: 12px 16px;
}
[data-testid="stMetricLabel"] { color: #8888AA; font-size: 0.75rem; }
[data-testid="stMetricValue"] { color: #00D4FF; font-size: 1.4rem; font-weight: 700; }
[data-testid="stMetricDelta"] { font-size: 0.75rem; }

/* ── Headers ── */
h1 { color: #00D4FF; border-bottom: 2px solid #00D4FF22; padding-bottom: 6px; }
h2 { color: #CCCCEE; }
h3 { color: #AAAACC; }

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #00D4FF22, #00D4FF44);
    border: 1px solid #00D4FF;
    color: #00D4FF;
    border-radius: 6px;
    font-weight: 600;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #00D4FF44, #00D4FF66);
    border-color: #00FFCC;
    color: #00FFCC;
}

/* ── Sliders ── */
.stSlider [data-baseweb="slider"] { accent-color: #00D4FF; }

/* ── DataFrames / tables ── */
[data-testid="stDataFrame"] {
    border: 1px solid #2A2A3E;
    border-radius: 6px;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    background: #1A1A2E;
    border: 1px solid #2A2A3E;
    border-radius: 8px;
}

/* ── Tabs ── */
[data-baseweb="tab-list"] { background: #13131F; border-bottom: 1px solid #2A2A3E; }
[data-baseweb="tab"]       { color: #8888AA; }
[aria-selected="true"][data-baseweb="tab"] { color: #00D4FF; border-bottom: 2px solid #00D4FF; }

/* ── Info / warning / success boxes ── */
.stAlert { border-radius: 6px; }

/* ── Code blocks ── */
code { background: #1A1A2E; color: #00D4FF; padding: 2px 5px; border-radius: 4px; }
pre  { background: #1A1A2E; border: 1px solid #2A2A3E; border-radius: 8px; }

/* ── Dividers ── */
hr { border-color: #2A2A3E; }

/* ── Select / number inputs ── */
[data-baseweb="select"] > div,
[data-baseweb="input"]  > div {
    background: #1A1A2E;
    border-color: #2A2A3E;
}
</style>
"""

# ---------------------------------------------------------------------------
# Mobile-responsive CSS (separate constant so pages can inject independently)
# ---------------------------------------------------------------------------

MOBILE_CSS = """
<style>
/* ============================================================
   MOBILE RESPONSIVE — breakpoint 768px
   Call inject_mobile_css() on every page for consistent scaling
   ============================================================ */

/* ── Mobile: main container ── */
@media screen and (max-width: 768px) {
    .main .block-container {
        padding-top: 0.75rem !important;
        padding-left: 0.5rem  !important;
        padding-right: 0.5rem !important;
        max-width: 100vw      !important;
    }
}

/* ── Mobile: typography scale-down ── */
@media screen and (max-width: 768px) {
    h1 { font-size: 1.35rem !important; }
    h2 { font-size: 1.15rem !important; }
    h3 { font-size: 1.0rem  !important; }
    p, li { font-size: 0.875rem; }
}

/* ── Mobile: metric cards ── */
@media screen and (max-width: 768px) {
    [data-testid="stMetric"] {
        padding: 8px 10px !important;
    }
    [data-testid="stMetricValue"] { font-size: 1.05rem !important; }
    [data-testid="stMetricLabel"] { font-size: 0.65rem !important; }
    [data-testid="stMetricDelta"] { font-size: 0.65rem !important; }
}

/* ── Mobile: DataFrames — horizontal scroll ── */
@media screen and (max-width: 768px) {
    [data-testid="stDataFrame"],
    [data-testid="stDataFrame"] > div,
    .dvn-scroller {
        overflow-x: auto                  !important;
        -webkit-overflow-scrolling: touch !important;
        max-width: calc(100vw - 1rem)     !important;
    }
}

/* ── Mobile: Plotly charts — full width ── */
@media screen and (max-width: 768px) {
    [data-testid="stPlotlyChart"],
    .js-plotly-plot,
    .plot-container {
        width:     100%  !important;
        max-width: 100vw !important;
    }
    .js-plotly-plot .plotly svg {
        width:  100% !important;
        height: auto !important;
    }
}

/* ── Mobile: columns — stack on very small screens ── */
@media screen and (max-width: 480px) {
    [data-testid="column"] {
        width:     100% !important;
        flex:      1 1 100% !important;
        min-width: 100% !important;
    }
}

/* ── Mobile: tabs — horizontal scroll, smaller text ── */
@media screen and (max-width: 768px) {
    [data-baseweb="tab-list"] {
        overflow-x: auto                  !important;
        -webkit-overflow-scrolling: touch !important;
        flex-wrap: nowrap                 !important;
    }
    [data-baseweb="tab"] {
        font-size:   0.75rem !important;
        padding:     6px 8px !important;
        white-space: nowrap  !important;
    }
}

/* ── Mobile: buttons — full width ── */
@media screen and (max-width: 768px) {
    .stButton > button {
        width:     100%     !important;
        font-size: 0.875rem !important;
        padding:   8px 12px !important;
    }
}

/* ── Mobile: code / pre blocks ── */
@media screen and (max-width: 768px) {
    pre {
        font-size:   0.75rem    !important;
        white-space: pre-wrap   !important;
        word-break:  break-word !important;
        overflow-x:  auto       !important;
    }
    code { font-size: 0.75rem !important; }
}

/* ── Mobile: caption / small text ── */
@media screen and (max-width: 768px) {
    .stCaption, small { font-size: 0.7rem !important; }
}

/* ── Mobile: sidebar — hidden by default, overlays when opened ──
   On narrow viewports the sidebar slides in from the left only when
   the user taps the hamburger toggle (aria-expanded="true").        */
@media screen and (max-width: 768px) {
    section[data-testid="stSidebar"] {
        transform:  translateX(-110%)           !important;
        transition: transform 0.3s ease         !important;
        position:   fixed                       !important;
        top:        0                           !important;
        left:       0                           !important;
        height:     100vh                       !important;
        width:      min(85vw, 360px)            !important;
        min-width:  unset                       !important;
        z-index:    999                         !important;
        box-shadow: 4px 0 24px rgba(0,0,0,0.6) !important;
    }
    section[data-testid="stSidebar"][aria-expanded="true"] {
        transform: translateX(0) !important;
    }
    [data-testid="stSidebar"] .stSlider,
    [data-testid="stSidebar"] .stSelectbox,
    [data-testid="stSidebar"] .stNumberInput {
        font-size: 0.875rem !important;
    }
}

/* ── Tablet (769–1024px): mild tuning ── */
@media screen and (min-width: 769px) and (max-width: 1024px) {
    .main .block-container {
        padding-left:  1rem !important;
        padding-right: 1rem !important;
    }
    [data-testid="stMetricValue"] { font-size: 1.2rem !important; }
    [data-testid="stMetricLabel"] { font-size: 0.7rem !important; }
    [data-testid="stMetricDelta"] { font-size: 0.7rem !important; }
}
</style>
"""


def inject_css() -> None:
    """Inject the global dark-theme CSS plus mobile responsive CSS."""
    st.markdown(DARK_CSS,   unsafe_allow_html=True)
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)


def inject_mobile_css() -> None:
    """
    Inject only the mobile-responsive CSS media queries.

    Call this at the top of every page (in addition to inject_css / page_header)
    so that mobile scaling is guaranteed regardless of page entry point.
    Injecting the same CSS block twice is harmless — browsers deduplicate rules.
    """
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Reusable UI components
# ---------------------------------------------------------------------------

def page_header(title: str, subtitle: str = "") -> None:
    """Render a styled page title and optional subtitle."""
    inject_css()
    st.markdown(f"# {title}")
    if subtitle:
        st.markdown(f"<p style='color:#8888AA; margin-top:-12px;'>{subtitle}</p>",
                    unsafe_allow_html=True)
    st.divider()


def metric_row(metrics: list[dict]) -> None:
    """
    Render a row of st.metric cards.

    Args:
        metrics: List of dicts with keys 'label', 'value', and optionally 'delta'.
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            st.metric(
                label=m["label"],
                value=m["value"],
                delta=m.get("delta"),
                delta_color=m.get("delta_color", "normal"),
            )


def colored_badge(text: str, color: str = "#00D4FF") -> str:
    """Return an HTML badge span for inline use in st.markdown()."""
    return (
        f"<span style='background:{color}22; color:{color}; "
        f"border:1px solid {color}; border-radius:4px; "
        f"padding:2px 8px; font-size:0.8rem; font-weight:600;'>{text}</span>"
    )


def section_header(title: str, description: str = "") -> None:
    """Render a consistent section sub-header with optional description."""
    st.markdown(f"### {title}")
    if description:
        st.caption(description)


def formula_block(formula: str, description: str = "") -> None:
    """Render a formula in a styled code block with an optional description."""
    if description:
        st.caption(description)
    st.code(formula, language="latex")


def warning_box(text: str) -> None:
    st.warning(f"⚠️  {text}")


def info_box(text: str) -> None:
    st.info(f"ℹ️  {text}")


def success_box(text: str) -> None:
    st.success(f"✅  {text}")
