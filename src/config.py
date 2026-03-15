"""
config.py — Centralized configuration and constants for the MBS Prepayment Engine.

All hard-coded parameters live here so they can be changed in one place.
In a production system many of these would be read from an environment file
or a configuration management service (e.g. Vault, AWS Parameter Store).
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR   = ROOT_DIR / "data"
SQL_DIR    = ROOT_DIR / "sql"
DB_PATH    = ROOT_DIR / "mbs_engine.db"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = f"sqlite:///{DB_PATH}"

# ---------------------------------------------------------------------------
# Mortgage math defaults
# ---------------------------------------------------------------------------
MONTHS_PER_YEAR: int   = 12
MAX_WAM_MONTHS:  int   = 360   # 30-year fixed-rate mortgage cap

# ---------------------------------------------------------------------------
# CPR / prepayment model tuning parameters
# ---------------------------------------------------------------------------
# Refinancing incentive sensitivity: how fast CPR accelerates as the
# mortgage rate falls below the pool WAC.  A sensitivity of 5 produces a
# steeper S-curve, meaning a 50bp move from at-the-money is enough to
# produce a meaningful CPR change and exhibit negative convexity.
REFI_SENSITIVITY:   float = 5.0   # CPR multiplier per 100bp of incentive

# Seasoning ramp: PSA convention assumes prepays ramp linearly over 30 months
# from 0% to 100% of the specified CPR.
PSA_RAMP_MONTHS:    int   = 30

# Baseline (housing turnover) CPR floor — even at zero refinancing incentive,
# owners sell / move at roughly 4-6% per year.
BASELINE_CPR:       float = 0.05  # 5% CPR floor

# Absolute CPR ceiling regardless of incentive
MAX_CPR:            float = 0.60  # 60% CPR cap

# Loan balance multipliers: larger loans prepay faster (more sensitive to
# rate moves); very small loans are less likely to refinance due to cost.
LOAN_SIZE_MULTIPLIERS = {
    "small":  0.80,   # < ~$150k; less refi-responsive
    "medium": 1.00,   # $150k-$500k; benchmark
    "large":  1.20,   # > $500k; jumbo-like; fast prepay
}

# Geography multipliers: California / coastal metros historically prepay
# faster than Midwest / rural markets.
GEOGRAPHY_MULTIPLIERS = {
    "high":   1.20,   # coastal / high-cost markets
    "medium": 1.00,   # national benchmark
    "low":    0.80,   # rural / rate-insensitive markets
}

# Seasonality: spring/summer housing market is more active.
# Index by calendar month (1 = Jan, 12 = Dec).
SEASONALITY_MULTIPLIERS = {
    1:  0.85,  # Jan — slow
    2:  0.90,  # Feb
    3:  1.00,  # Mar
    4:  1.10,  # Apr
    5:  1.20,  # May — peak
    6:  1.20,  # Jun — peak
    7:  1.15,  # Jul
    8:  1.10,  # Aug
    9:  1.00,  # Sep
    10: 0.95,  # Oct
    11: 0.90,  # Nov
    12: 0.85,  # Dec — slow
}

# ---------------------------------------------------------------------------
# Risk / pricing parameters
# ---------------------------------------------------------------------------
# Parallel rate shock (in decimal) used to compute effective duration /
# convexity via finite differences.  50bp is the standard for MBS because
# smaller shocks don't materially move CPR off the turnover floor, causing
# cash-flow projections to be nearly identical and masking the option effect.
DURATION_SHOCK:     float = 0.0050   # 50bp (0.50%)

# DV01 of a stylized 10Y Treasury futures contract ($/contract/bp).
# A $100k notional 10Y note at ~8yr duration gives roughly $800/bp DV01.
# We use a round number approximation; a real desk would use Bloomberg DV01.
TREASURY_10Y_DV01:  float = 850.0    # $ per contract per 1bp

# Par value for pool pricing convention
POOL_PAR:           float = 100.0    # price expressed as % of face

# ---------------------------------------------------------------------------
# Scenario definitions (mirror SQL table, used for in-memory runs)
# ---------------------------------------------------------------------------
DEFAULT_SCENARIOS = [
    {"name": "Base",           "rate_shift_bp":   0, "slope_shift_bp":   0, "vol_shift": 0.0},
    {"name": "Down 50bp",      "rate_shift_bp": -50, "slope_shift_bp":   0, "vol_shift": 0.0},
    {"name": "Down 100bp",     "rate_shift_bp":-100, "slope_shift_bp":   0, "vol_shift": 0.0},
    {"name": "Up 50bp",        "rate_shift_bp":  50, "slope_shift_bp":   0, "vol_shift": 0.0},
    {"name": "Up 100bp",       "rate_shift_bp": 100, "slope_shift_bp":   0, "vol_shift": 0.0},
    {"name": "Bull Steepener", "rate_shift_bp": -50, "slope_shift_bp":  25, "vol_shift": 0.0},
    {"name": "Bear Flattener", "rate_shift_bp":  50, "slope_shift_bp": -25, "vol_shift": 0.0},
    {"name": "Vol Shock",      "rate_shift_bp":   0, "slope_shift_bp":   0, "vol_shift": 0.5},
]

# ---------------------------------------------------------------------------
# App display
# ---------------------------------------------------------------------------
APP_TITLE      = "MBS Prepayment, Cash Flow & Hedging Engine"
APP_SUBTITLE   = "Fixed Income Relative Value Analytics | Garda Capital Partners"
CHART_TEMPLATE = "plotly_dark"
PRIMARY_COLOR  = "#00D4FF"   # Accent cyan
SUCCESS_COLOR  = "#00FF88"   # Green metric
WARNING_COLOR  = "#FFB800"   # Amber warning
DANGER_COLOR   = "#FF4444"   # Red risk
GRID_COLOR     = "#2A2A3E"
