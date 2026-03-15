-- =============================================================================
-- MBS Prepayment Engine -- Seed Data
-- =============================================================================
-- Provides a realistic starting pool so the app is immediately usable.
-- Pool "FNMA_30Y_SAMPLE" is modeled loosely after a seasoned FNMA 30-year
-- 6.0% pool with moderate prepayment history.
-- Rate history reflects a stylized 2023-2024 environment.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- pool_static: Sample FNMA 30-year pool
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO pool_static (
    pool_id, pool_name, original_balance, wac, wam, pool_age,
    servicing_fee, loan_size_bucket, geography_bucket,
    burnout_factor, turnover_factor, seasonality_factor
) VALUES (
    'FNMA_30Y_6PCT',
    'FNMA 30Y 6.0% Sample Pool',
    100000000,   -- $100 million original balance
    0.065,       -- 6.5% WAC (gross coupon)
    360,         -- 30-year pool, 360 months original WAM
    24,          -- 24 months seasoned
    0.0025,      -- 25bp servicing/g-fee
    'medium',    -- medium loan size ($300k-$600k range)
    'medium',    -- medium prepay geography
    0.85,        -- slight burnout (pool has seen some refinancing)
    1.0,         -- neutral turnover
    1.0          -- neutral seasonality starting point
);

-- ---------------------------------------------------------------------------
-- rate_history: Representative rate observations
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO rate_history (as_of_date, current_mortgage_rate, treasury_10y, treasury_2y, sofr, notes) VALUES
    ('2023-01-01', 0.0648, 0.0353, 0.0448, 0.0430, 'Jan 2023 rate environment'),
    ('2023-04-01', 0.0671, 0.0353, 0.0484, 0.0481, 'Q1 2023 end'),
    ('2023-07-01', 0.0699, 0.0388, 0.0488, 0.0516, 'Q2 2023 end'),
    ('2023-10-01', 0.0773, 0.0473, 0.0509, 0.0530, 'Rates peak Q3 2023'),
    ('2024-01-01', 0.0696, 0.0399, 0.0438, 0.0533, 'Jan 2024'),
    ('2024-04-01', 0.0690, 0.0431, 0.0471, 0.0531, 'Q1 2024 end'),
    ('2024-07-01', 0.0670, 0.0427, 0.0453, 0.0533, 'Q2 2024 end'),
    ('2024-10-01', 0.0630, 0.0392, 0.0384, 0.0480, 'Post-Fed-cut environment'),
    ('2025-01-01', 0.0695, 0.0459, 0.0428, 0.0433, 'Jan 2025 rates rise again'),
    ('2025-04-01', 0.0672, 0.0421, 0.0400, 0.0430, 'Q1 2025 end'),
    ('2025-07-01', 0.0648, 0.0400, 0.0385, 0.0410, 'Mid 2025'),
    ('2026-01-01', 0.0650, 0.0410, 0.0390, 0.0400, 'Current environment');

-- ---------------------------------------------------------------------------
-- scenario_definitions: Standard rate shock scenarios
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO scenario_definitions (scenario_name, rate_shift_bp, slope_shift_bp, vol_shift, description) VALUES
    ('Base',             0.0,    0.0,   0.0,  'No rate change; current market conditions'),
    ('Down 50bp',       -50.0,   0.0,   0.0,  'Parallel curve shift down 50 basis points'),
    ('Down 100bp',     -100.0,   0.0,   0.0,  'Parallel curve shift down 100 basis points'),
    ('Up 50bp',          50.0,   0.0,   0.0,  'Parallel curve shift up 50 basis points'),
    ('Up 100bp',        100.0,   0.0,   0.0,  'Parallel curve shift up 100 basis points'),
    ('Bull Steepener',  -50.0,   25.0,  0.0,  'Front end rallies more than long end; curve steepens'),
    ('Bear Flattener',   50.0,  -25.0,  0.0,  'Long end sells off more; curve flattens'),
    ('Vol Shock',         0.0,   0.0,   0.5,  'Rate unchanged but implied vol rises 50%; wider OAS proxy');

-- ---------------------------------------------------------------------------
-- cpr_assumptions: Default CPR model parameters for each pool/scenario combo
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO cpr_assumptions (pool_id, scenario_id, refi_multiplier, seasoning_ramp_months, baseline_cpr, max_cpr)
SELECT
    'FNMA_30Y_6PCT' AS pool_id,
    scenario_id,
    CASE scenario_name
        WHEN 'Down 100bp'    THEN 1.40
        WHEN 'Down 50bp'     THEN 1.20
        WHEN 'Up 100bp'      THEN 0.60
        WHEN 'Up 50bp'       THEN 0.80
        WHEN 'Bull Steepener' THEN 1.10
        WHEN 'Bear Flattener' THEN 0.85
        WHEN 'Vol Shock'     THEN 0.90
        ELSE 1.00
    END AS refi_multiplier,
    30  AS seasoning_ramp_months,
    0.04 AS baseline_cpr,
    0.60 AS max_cpr
FROM scenario_definitions;
