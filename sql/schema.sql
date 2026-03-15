-- =============================================================================
-- MBS Prepayment Engine -- Database Schema
-- =============================================================================
-- Stores pool static data, rate assumptions, scenario definitions, CPR
-- assumptions, projected cash flows, risk results, and audit trail of runs.
-- All monetary values stored in whole dollars; rates stored as decimals
-- (e.g. 0.065 = 6.5%).
-- =============================================================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ---------------------------------------------------------------------------
-- pool_static: One row per pool describing the underlying mortgage collateral
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pool_static (
    pool_id             TEXT    PRIMARY KEY,
    pool_name           TEXT    NOT NULL,
    original_balance    REAL    NOT NULL,   -- original unpaid principal balance ($)
    wac                 REAL    NOT NULL,   -- weighted average coupon (decimal)
    wam                 INTEGER NOT NULL,   -- weighted average maturity (months)
    pool_age            INTEGER NOT NULL DEFAULT 0, -- seasoning in months
    servicing_fee       REAL    NOT NULL DEFAULT 0.0025, -- servicing/g-fee strip (decimal)
    loan_size_bucket    TEXT    NOT NULL DEFAULT 'medium', -- small / medium / large
    geography_bucket    TEXT    NOT NULL DEFAULT 'medium', -- high / medium / low prepay region
    burnout_factor      REAL    NOT NULL DEFAULT 1.0,  -- 0-1 scalar dampening refi response
    turnover_factor     REAL    NOT NULL DEFAULT 1.0,  -- geographic housing turnover multiplier
    seasonality_factor  REAL    NOT NULL DEFAULT 1.0,  -- seasonal prepay adjustment
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- rate_history: Time series of benchmark rates used for refi incentive calcs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rate_history (
    rate_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of_date          TEXT    NOT NULL,
    current_mortgage_rate REAL  NOT NULL,   -- prevailing primary mortgage rate (decimal)
    treasury_10y        REAL    NOT NULL,   -- 10Y Treasury yield (decimal)
    treasury_2y         REAL    NOT NULL,   -- 2Y Treasury yield (decimal)
    sofr                REAL    NOT NULL DEFAULT 0.0,
    notes               TEXT,
    UNIQUE(as_of_date)
);

-- ---------------------------------------------------------------------------
-- scenario_definitions: Named rate shock scenarios applied to the base curve
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scenario_definitions (
    scenario_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_name       TEXT    NOT NULL UNIQUE,
    rate_shift_bp       REAL    NOT NULL DEFAULT 0.0, -- parallel shift in basis points
    slope_shift_bp      REAL    NOT NULL DEFAULT 0.0, -- 2s10s steepening (+) or flattening (-) in bp
    vol_shift           REAL    NOT NULL DEFAULT 0.0, -- implied vol shift (scalar multiplier)
    description         TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- cpr_assumptions: Per-pool, per-scenario CPR model parameter overrides
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cpr_assumptions (
    assumption_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_id             TEXT    NOT NULL REFERENCES pool_static(pool_id),
    scenario_id         INTEGER NOT NULL REFERENCES scenario_definitions(scenario_id),
    refi_multiplier     REAL    NOT NULL DEFAULT 1.0, -- scales sensitivity of refi incentive
    seasoning_ramp_months INTEGER NOT NULL DEFAULT 30, -- months to full seasoning
    baseline_cpr        REAL    NOT NULL DEFAULT 0.06,  -- minimum/floor CPR (decimal)
    max_cpr             REAL    NOT NULL DEFAULT 0.60,  -- cap on CPR (decimal)
    UNIQUE(pool_id, scenario_id)
);

-- ---------------------------------------------------------------------------
-- projected_cashflows: Month-by-month cash flow output for a pool/scenario
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projected_cashflows (
    cf_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL REFERENCES model_runs(run_id),
    pool_id             TEXT    NOT NULL REFERENCES pool_static(pool_id),
    scenario_id         INTEGER NOT NULL REFERENCES scenario_definitions(scenario_id),
    period              INTEGER NOT NULL,   -- month number (1-based)
    beginning_balance   REAL    NOT NULL,
    scheduled_payment   REAL    NOT NULL,
    interest            REAL    NOT NULL,
    scheduled_principal REAL    NOT NULL,
    cpr                 REAL    NOT NULL,
    smm                 REAL    NOT NULL,
    prepayment          REAL    NOT NULL,
    total_principal     REAL    NOT NULL,
    ending_balance      REAL    NOT NULL,
    total_cashflow      REAL    NOT NULL,   -- interest + total_principal
    UNIQUE(run_id, pool_id, scenario_id, period)
);

-- ---------------------------------------------------------------------------
-- risk_results: Scalar risk metrics per pool/scenario/run
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_results (
    result_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL REFERENCES model_runs(run_id),
    pool_id             TEXT    NOT NULL REFERENCES pool_static(pool_id),
    scenario_id         INTEGER NOT NULL REFERENCES scenario_definitions(scenario_id),
    wal                 REAL,   -- weighted average life (years)
    price               REAL,   -- modeled price (% of par)
    eff_duration        REAL,   -- effective duration (years)
    convexity           REAL,   -- effective convexity
    dv01                REAL,   -- dollar value of 1bp move ($)
    hedge_units         REAL,   -- notional 10Y TSY futures required to hedge
    UNIQUE(run_id, pool_id, scenario_id)
);

-- ---------------------------------------------------------------------------
-- model_runs: Audit log of every engine invocation
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_runs (
    run_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_id             TEXT    NOT NULL,
    run_timestamp       TEXT    NOT NULL DEFAULT (datetime('now')),
    discount_rate       REAL    NOT NULL,   -- base discount rate used for pricing
    num_scenarios       INTEGER NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'pending', -- pending/complete/error
    error_message       TEXT
);
