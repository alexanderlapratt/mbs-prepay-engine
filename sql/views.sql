-- =============================================================================
-- MBS Prepayment Engine -- Analytical Views
-- =============================================================================
-- These views make it easy to query the most recent run's results and join
-- pool metadata with cash-flow and risk outputs for dashboard consumption.
-- =============================================================================

-- Latest completed run per pool
CREATE VIEW IF NOT EXISTS v_latest_runs AS
SELECT
    mr.pool_id,
    MAX(mr.run_id) AS latest_run_id,
    MAX(mr.run_timestamp) AS latest_run_time
FROM model_runs mr
WHERE mr.status = 'complete'
GROUP BY mr.pool_id;

-- ---------------------------------------------------------------------------
-- v_cashflow_summary: Full cash-flow grid joined to scenario names
-- ---------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_cashflow_summary AS
SELECT
    cf.pool_id,
    sd.scenario_name,
    cf.period,
    cf.beginning_balance,
    cf.interest,
    cf.scheduled_principal,
    cf.prepayment,
    cf.total_principal,
    cf.ending_balance,
    cf.total_cashflow,
    cf.cpr,
    cf.smm
FROM projected_cashflows cf
JOIN scenario_definitions sd  ON sd.scenario_id  = cf.scenario_id
JOIN v_latest_runs lr         ON lr.pool_id       = cf.pool_id
                              AND lr.latest_run_id = cf.run_id;

-- ---------------------------------------------------------------------------
-- v_risk_summary: Risk metrics joined to pool metadata and scenario names
-- ---------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_risk_summary AS
SELECT
    rr.pool_id,
    ps.pool_name,
    ps.wac,
    ps.wam,
    ps.pool_age,
    sd.scenario_name,
    sd.rate_shift_bp,
    sd.slope_shift_bp,
    rr.wal,
    rr.price,
    rr.eff_duration,
    rr.convexity,
    rr.dv01,
    rr.hedge_units
FROM risk_results rr
JOIN pool_static ps           ON ps.pool_id    = rr.pool_id
JOIN scenario_definitions sd  ON sd.scenario_id = rr.scenario_id
JOIN v_latest_runs lr         ON lr.pool_id     = rr.pool_id
                              AND lr.latest_run_id = rr.run_id;

-- ---------------------------------------------------------------------------
-- v_cpr_by_scenario: Annualized CPR per period across scenarios
-- ---------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_cpr_by_scenario AS
SELECT
    pool_id,
    scenario_name,
    period,
    ROUND(cpr * 100, 2) AS cpr_pct,
    ROUND(smm * 100, 4) AS smm_pct
FROM v_cashflow_summary;

-- ---------------------------------------------------------------------------
-- v_pool_overview: Single-row summary of each pool with current balance
-- ---------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_pool_overview AS
SELECT
    ps.pool_id,
    ps.pool_name,
    ps.original_balance,
    ps.wac,
    ps.wam,
    ps.pool_age,
    ps.servicing_fee,
    ROUND(ps.wac - ps.servicing_fee, 6) AS net_coupon,
    ps.loan_size_bucket,
    ps.geography_bucket,
    ps.burnout_factor
FROM pool_static ps;
