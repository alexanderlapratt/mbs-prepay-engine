# MBS Prepayment, Cash Flow & Hedging Engine

> **A fully deployable Python/Streamlit analytics platform for fixed-rate agency MBS.**
> Built to demonstrate quantitative interest-rate and prepayment modeling for fixed income relative value.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32%2B-red)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

**Live App:** `https://mbs-prepay-engine-8ts8bbjxfnf8xkeel5gq3w.streamlit.app` _(deploy via Streamlit Community Cloud)_

---

## Project Goal

Agency MBS (mortgage-backed securities) are the largest fixed-income market in the world, yet their analytics are fundamentally different from bullet bonds.  The embedded prepayment option creates **negative convexity** — a property that makes standard duration/convexity tools inadequate.

This project builds a complete, deployable prepayment and cash-flow engine that:
- Supports both user-defined stylized pools and real loan-level data from the **Fannie Mae Single-Family Loan Performance Data (SFLP), 2024 Q1** (272,963 loans, $91.1B in originations)
- Lets a user configure a stylized mortgage pool or load a real FNMA rate bucket with one click
- Projects monthly cash flows across 8 rate scenarios
- Computes WAL, effective duration, convexity, DV01, and hedge ratios
- Explains every formula and the key limitations vs. a production system

---

## Why Mortgages Are Different from Normal Bonds (Negative Convexity)

A standard "bullet" bond has two nice properties:
1. **Fixed cash flows** → analytical duration and convexity formulas work exactly.
2. **Positive convexity** → the bond appreciates *faster* in rate rallies than it depreciates in selloffs.

Mortgages break both:

**Amortization:** The borrower repays principal gradually over the loan life.  The investor gets capital back every month, not at maturity.

**Embedded call option:** The borrower can prepay at par at any time.  When rates fall below their coupon, they refinance — returning capital at par precisely when the investor must reinvest at lower rates.

**Negative convexity:**
- Rates rally → borrowers refinance → pool shortens → price appreciation capped (pool "calls away").
- Rates rise → fewer refinancings → pool extends → price falls faster than a bullet of the same initial duration.

Both directions underperform a comparable bullet bond.  The yield spread on MBS vs. Treasuries (the Z-spread or OAS) compensates investors for this asymmetry.

---

## Model Architecture

```
Pool Inputs (WAC, WAM, Pool Age, Balance, Rate)
        │
        ▼
┌───────────────────┐
│  mortgage_math.py  │  Scheduled payment / interest / principal (Steps 1–3)
└───────────────────┘
        │
        ▼
┌───────────────────────────────┐
│          cpr_model.py          │  Multi-factor CPR (Step 4)
│  • Refi incentive (S-curve)    │
│  • Seasoning ramp (PSA)        │
│  • Burnout dampening           │
│  • Housing turnover floor      │
│  • Calendar seasonality        │
│  • Loan size / geography       │
└───────────────────────────────┘
        │
        ▼
┌──────────────────────┐
│  cashflow_engine.py   │  SMM → Prepayment → Balance → WAL (Steps 5–9)
└──────────────────────┘
        │
        ▼
┌─────────────────────┐
│   risk_engine.py     │  Price, Eff. Duration, Convexity, DV01 (Steps 10–11)
│   (bump-and-reprice) │
└─────────────────────┘
        │
        ▼
┌──────────────────────┐
│   hedge_engine.py     │  Hedge units, notional, convexity cost
└──────────────────────┘
        │
        ▼
┌──────────────────────────┐
│   scenario_engine.py      │  Orchestrates 8 standard rate scenarios
└──────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────┐
│          Streamlit Dashboard (5 pages)           │
│  1. Pool Setup    2. Scenario Analysis           │
│  3. CF Waterfall  4. Risk & Hedging              │
│                   5. Model Documentation         │
└─────────────────────────────────────────────────┘
```

---

## Complete Formula Reference

### Step 1: Scheduled Monthly Payment
```
P = B × r / (1 − (1 + r)^(−N))
```
B = outstanding balance, r = WAC/12, N = remaining months

### Step 2: Monthly Interest (investor receives net coupon)
```
Interest_t = Balance_{t-1} × NetWAC / 12
NetWAC = GrossWAC − ServicingFee − G-Fee
```

### Step 3: Scheduled Principal
```
SchedPrin_t = GrossPayment_t − GrossInterest_t
```

### Step 4: CPR Multi-Factor Model
```
RefiCPR = max(0, MaxRefi / (1 + exp(−k × Incentive)) − MaxRefi/2) × RefiMultiplier
Incentive = WAC − CurrentMortgageRate

TurnoverCPR = BaselineCPR × TurnoverFactor

CPR = clamp(
    (RefiCPR + TurnoverCPR)
    × SeasoningMult × BurnoutFactor
    × LoanSizeMult × GeoMult × CalMult × SeasonalityFactor,
    TurnoverFloor,
    MaxCPR
)
```

### Step 5: SMM from CPR
```
SMM_t = 1 − (1 − CPR_t)^(1/12)
```

### Step 6: Unscheduled Prepayment
```
Prepayment_t = SMM_t × (Balance_{t-1} − SchedPrin_t)
```

### Step 7: Total Principal
```
TotalPrincipal_t = SchedPrin_t + Prepayment_t
```

### Step 8: Ending Balance
```
Balance_t = Balance_{t-1} − TotalPrincipal_t
```

### Step 9: WAL
```
WAL = Σ(t/12 × TotalPrincipal_t) / CurrentBalance   [years]
```

### Step 10: Effective Duration and Convexity (Bump-and-Reprice)
```
Price = Σ(TotalCF_t / (1 + r/12)^t) / CurrentBalance × 100

EffDuration = (Price_dn − Price_up) / (2 × Price_base × Δr)
Convexity   = (Price_dn + Price_up − 2 × Price_base) / (Price_base × Δr²)
```
where Δr = 25bp and Price_up/dn are re-projected at ±Δr

### Step 11: DV01 and Hedge Ratio
```
DV01 = Price_base × EffDuration / 10,000 × FaceValue   [$]
HedgeUnits = DV01_pool / DV01_10Y_futures
```

---

## Dashboard Screenshots

_[Screenshots to be added after deployment]_

| Page | Description |
|------|-------------|
| Pool Setup | Pool parameters, amortization preview, balance decay |
| Scenario Analysis | CPR by scenario, S-curve, CPR driver decomposition |
| Cash Flow Waterfall | Interest/principal/prepayment stacked area, remaining balance |
| Risk & Hedging | Price, WAL, duration, convexity, DV01, hedge units |
| Model Documentation | All formulas, assumptions, limitations, real-data roadmap |

---

## Key Findings: Duration Behavior Across Rate Scenarios

Running the engine on the **Fannie Mae 6–7% bucket** (WAC 6.609%, 2024 Q1, $100M representative pool):

| Scenario   | WAL (yr) | Price   | Eff. Duration | Convexity  |
|------------|--------:|--------:|--------------:|-----------:|
| Down 100bp |    2.38  | 101.849 |         2.040 |   23.976   |
| Down 50bp  |    2.98  | 100.952 |         2.671 | –152.286   |
| Base       |    7.14  |  99.372 |         5.386 | –770.885   |
| Up 50bp    |   11.22  |  95.738 |         7.076 |  168.794   |
| Up 100bp   |   11.22  |  92.553 |         6.684 |   79.259   |

**Key observation:** The pool extends 3+ years in a 100bp selloff and contracts 2.5+ years in a 100bp rally.  This extension/contraction asymmetry — negative convexity — means duration risk is greater in selloffs, which is when investors can least afford it.

---

## Limitations

- CPR model is rule-based (not empirically calibrated to historical remittance data)
- Pricing uses flat yield discounting, not OAS-adjusted spot curve
- Burnout modeled as a static scalar (not dynamic path-dependent state)
- No loan-level heterogeneity
- Rate scenarios assume instantaneous shifts (not path-dependent)
- Single 10Y Treasury futures instrument for hedging (no key-rate hedge)

---

## What I Would Do With Real Data

### OAS vs. Yield-Based Duration
Build a stochastic short-rate model (Hull-White or BGM/LMM), simulate thousands of rate paths, run path-dependent prepayment projections, and compute the OAS (option-adjusted spread) that equates modeled price to market price.  OAS duration is the correct hedge metric.

### Loan-Level vs. Pool-Level Modeling
Use FNMA/FHLMC public loan-level datasets to fit separate CPR models by coupon bucket, LTV cohort, FICO band, and loan size.  Build a heterogeneous pool model that aggregates loan-level forecasts.

### Dealer Prepayment Model Services
Subscribe to Andrew Davidson & Co. (AD&Co.), Intex, or Bloomberg MBS Analytics for historically-calibrated CPR curves, CMO tranche waterfalls, and TBA pricing.

### Actual TBA Prices
Use Bloomberg TBA runs or BGN composite prices as the primary reference instead of model-derived prices.  Trade specified pools at pay-ups vs. TBA for favorable pool characteristics (low loan balance, high LTV, NY geography).

### Real Calibration
Fit the CPR S-curve parameters via maximum likelihood to FNMA/FHLMC monthly remittance files (5+ years of actual CPR by coupon/vintage/WALA), validate out-of-sample, and apply desk trader overrides for current credit conditions.

---

## Real Data Integration

### Data Source

The engine ingests real loan-level data from the **Fannie Mae Single-Family Loan Performance (SFLP) Dataset**, 2024 Q1.

Available free at: [capitalmarkets.fanniemae.com](https://capitalmarkets.fanniemae.com/credit-risk-transfer/single-family-credit-risk-transfer/fannie-mae-single-family-loan-performance-data)

The dataset contains loan-level performance data for fixed-rate agency MBS pools with 110 pipe-delimited fields and no column headers.

### Data Cleaning Pipeline (`src/ingest_fannie_mae.py`)

The ingestion script performs the following steps:

1. Reads the raw pipe-delimited CSV with no headers
2. Assigns the 110 standard SFLP column names
3. Corrects an offset in the raw file layout (current UPB field at position 11 requires a column label swap)
4. Filters to 30-year fixed-rate loans only (`ORIG_LOAN_TERM = 360`)
5. Removes loans with null `ORIG_INTEREST_RATE`, `ORIG_UPB`, or `ORIG_LOAN_TERM`
6. Removes loans with `ORIG_INTEREST_RATE` outside 2.0–12.0%
7. Removes loans with `ORIG_UPB <= 0`
8. Groups remaining loans into 5 rate buckets: 3–4%, 4–5%, 5–6%, 6–7%, 7%+
9. Computes pool-level aggregates per bucket: WAC (weighted by UPB), average LTV, average FICO, average loan size, total balance, loan count, top state

### Pool Profiles Output

| Bucket | Loans | WAC | Avg Loan | Avg LTV | Avg FICO | Total Balance | Top State |
|--------|------:|----:|--------:|--------:|--------:|----------:|------:|
| 3–4%   |       7 | 3.789% | $291.3K | 53.7% | 754 | $0.00B | LA |
| 4–5%   |   2,083 | 4.829% | $363.2K | 75.8% | 768 | $0.76B | TX |
| 5–6%   |  20,070 | 5.752% | $341.1K | 74.7% | 766 | $6.85B | TX |
| 6–7%   | 144,942 | 6.609% | $337.3K | 75.5% | 763 | $48.89B | TX |
| 7%+    | 105,861 | 7.440% | $326.9K | 76.9% | 755 | $34.60B | TX |

The 6–7% bucket dominates 2024 Q1 originations, reflecting the prevailing 30-year fixed mortgage rate environment of late 2023 / early 2024.

### How to Run the Ingestion Pipeline

```bash
# Download 2024Q1.csv from Fannie Mae SFLP or Kaggle
# Place it in your local directory
# Run the ingestion script
python src/ingest_fannie_mae.py
# Output saved to data/processed/fannie_mae_pool_profiles.csv
```

### How to Load Real Data in the App

1. Navigate to the **Pool Setup** page
2. Open the **"Load Real Fannie Mae Pool Data"** expander at the top
3. Select a rate bucket from the dropdown
4. Review the pool statistics (loans, WAC, LTV, FICO, balance)
5. Click **"Apply to Sidebar"**
6. Navigate to the **Dashboard** and click **Run Analysis**
7. All analytics now reflect real 2024 Q1 origination characteristics

---

## How to Run Locally

```bash
# Clone the repo
git clone https://github.com/alexanderlapratt/mbs-prepay-engine.git
cd mbs-prepay-engine

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# (Optional) Run the Fannie Mae data ingestion pipeline
# Requires 2024Q1.csv placed in your working directory
python src/ingest_fannie_mae.py
# Output: data/processed/fannie_mae_pool_profiles.csv

# Run the dashboard
streamlit run app/dashboard.py

# Run the tests
pytest tests/ -v
```

The app will be available at `http://localhost:8501`.

---

## Deploying to Streamlit Community Cloud

1. Push this repo to GitHub (public or private).
2. Go to [share.streamlit.io](https://share.streamlit.io) → New App.
3. Select repo, branch `main`, and set **Main file path** to `app/Dashboard.py`.
4. Click **Deploy** — no additional configuration required.

The `.streamlit/config.toml` file configures the dark theme and wide layout automatically.

**Deployed App:** `https://mbs-prepay-engine-8ts8bbjxfnf8xkeel5gq3w.streamlit.app`

---

## Project Structure

```
mbs-prepay-engine/
├── app/
│   ├── Dashboard.py              # Main entry point & sidebar controls
│   ├── pages/
│   │   ├── 1_Pool_Setup.py
│   │   ├── 2_Scenario_Analysis.py
│   │   ├── 3_Cashflow_Waterfall.py
│   │   ├── 4_Risk_and_Hedging.py
│   │   └── 5_Model_Documentation.py
│   └── components/
│       ├── charts.py             # All Plotly chart factory functions
│       ├── tables.py             # DataFrame formatting helpers
│       └── styles.py             # CSS injection and UI components
├── src/
│   ├── config.py                 # Constants and tuning parameters
│   ├── db.py                     # SQLite / SQLAlchemy layer
│   ├── data_loader.py            # Pool params builder, DataFrame helpers
│   ├── mortgage_math.py          # Core fixed-rate mortgage formulas
│   ├── cpr_model.py              # Multi-factor CPR model
│   ├── scenario_engine.py        # 8-scenario orchestration
│   ├── cashflow_engine.py        # Monthly CF projection + WAL
│   ├── risk_engine.py            # Duration, convexity, DV01
│   ├── hedge_engine.py           # Hedge ratio computation
│   └── utils.py                  # Shared helpers
├── sql/
│   ├── schema.sql                # SQLite table definitions
│   ├── seed.sql                  # Sample FNMA pool + scenarios
│   └── views.sql                 # Analytical views
├── tests/
│   ├── test_mortgage_math.py
│   ├── test_cpr_model.py
│   ├── test_cashflows.py
│   └── test_risk.py
├── requirements.txt
├── .streamlit/config.toml
└── README.md
```

---

## Author

**Alexander LaPratt**
Yale University — BS Computer Science & Mathematics (4.0 Major GPA)
[alexander.lapratt@yale.edu](mailto:alexander.lapratt@yale.edu)

_Built March 2026 as a technical demonstration of agency MBS analytics, incorporating real Fannie Mae Single-Family Loan Performance Data._
