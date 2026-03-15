"""
5_Model_Documentation.py — Full model documentation, formulas, assumptions, and limitations.

This page serves as both an academic reference and a transparency layer —
explaining exactly what the model does, why it makes the choices it does,
and what would be needed to make it production-grade.

Interview-ready: every section here should be discussable with the MBS desk,
credit desk, and deputy CIO in depth.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
from app.components.styles import inject_css, page_header, section_header

inject_css()
page_header("Model Documentation", "Architecture, formulas, assumptions, limitations, and next steps")

st.markdown("""
> **Purpose:** This page documents every formula, assumption, and known limitation of
> the MBS Prepayment, Cash Flow & Hedging Engine.  It is intended to be read alongside
> the interactive dashboard and should serve as a standalone reference for any
> quantitative discussion of agency MBS analytics.
""")

# ─────────────────────────────────────────────────────────────────────────────
# 1. What Makes MBS Different from Bullets
# ─────────────────────────────────────────────────────────────────────────────

section_header("1. Why Mortgages Are Different from Normal Bonds")

st.markdown("""
A standard fixed-rate bond (a "bullet") returns all principal at maturity and
pays a fixed coupon in between.  Duration is computable analytically; convexity
is always positive (price appreciation accelerates as rates fall).

Mortgages break both properties:

**Amortization:** Principal is returned gradually over the loan's life
(typically 30 years), not in a lump sum.  This means the investor's effective
maturity is much shorter than the stated WAM.

**Prepayment optionality:** The borrower holds an *embedded call option*:
they can prepay the outstanding balance at par at any time.  This option is
exercised most actively when rates fall below the mortgage coupon (refinancing).

The investor (MBS holder) is **short this call option**.  This creates
**negative convexity**:
- When rates fall → borrowers refinance → principal returned at par at the
  worst possible time (low reinvestment rates) → price appreciation is capped.
- When rates rise → borrowers don't refinance → pool duration extends → price
  falls faster than a bullet of equivalent initial duration.

This two-sided underperformance relative to a bullet is the fundamental
risk premium that MBS investors are compensated for.  The spread between
MBS yields and Treasuries (Z-spread, OAS) reflects this optionality cost.
""")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Cash-Flow Model Architecture
# ─────────────────────────────────────────────────────────────────────────────

section_header("2. Model Architecture")

st.markdown("""
```
Pool Inputs (WAC, WAM, Pool Age, Balance, Rate)
        │
        ▼
┌───────────────────┐
│  mortgage_math.py  │  → Scheduled payment, interest, principal (Steps 1-3)
└───────────────────┘
        │
        ▼
┌───────────────────┐
│    cpr_model.py    │  → Multi-factor CPR (Step 4)
│  Refi Incentive    │
│  Seasoning Ramp    │
│  Burnout           │
│  Turnover          │
│  Seasonality       │
│  Loan Size         │
│  Geography         │
└───────────────────┘
        │
        ▼
┌───────────────────────┐
│  cashflow_engine.py    │  → SMM, Prepayment, Total Principal, Balance (Steps 5-8)
│  Monthly projection    │  → WAL
└───────────────────────┘
        │
        ▼
┌───────────────────┐
│  risk_engine.py    │  → Price, Eff. Duration, Convexity, DV01 (Steps 9-11)
│  Bump-and-reprice  │  (finite differences on full CF re-projection)
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  hedge_engine.py   │  → Hedge units, notional, convexity cost estimate
└───────────────────┘
        │
        ▼
┌───────────────────────────┐
│  scenario_engine.py        │  → Orchestrates 8 rate scenarios
└───────────────────────────┘
```
""")

# ─────────────────────────────────────────────────────────────────────────────
# 3. All Formulas
# ─────────────────────────────────────────────────────────────────────────────

section_header("3. Complete Formula Reference")

with st.expander("📐 Step 1: Scheduled Monthly Payment", expanded=False):
    st.markdown("""
**Standard fixed-rate annuity formula:**

```
P = B × r / (1 − (1 + r)^(−N))
```

| Symbol | Meaning |
|--------|---------|
| P      | Scheduled monthly payment ($) |
| B      | Outstanding principal balance ($) |
| r      | Monthly gross coupon = WAC / 12 |
| N      | Remaining term in months (WAM − pool age) |

The payment P is fixed for the life of the loan.
""")

with st.expander("📐 Steps 2-3: Interest and Scheduled Principal"):
    st.markdown("""
**Monthly Interest (investor receives net coupon):**
```
Interest_t = Balance_{t-1} × NetWAC / 12
NetWAC = GrossWAC − ServicingFee − G-Fee
```

**Scheduled Principal:**
```
SchedPrin_t = GrossPayment_t − (Balance_{t-1} × GrossWAC / 12)
```
""")

with st.expander("📐 Step 4: CPR Multi-Factor Model"):
    st.markdown("""
**Refinancing component (logistic S-curve):**
```
Incentive = WAC − CurrentMortgageRate
RefiCPR = max(0, MaxRefi / (1 + exp(−k × Incentive)) − MaxRefi/2) × RefiMultiplier
```

**Turnover component (housing mobility floor):**
```
TurnoverCPR = BaselineCPR × TurnoverFactor
```

**Seasoning ramp (PSA-style):**
```
SeasoningMult = min(PoolAge / RampMonths, 1.0)
```

**Final CPR:**
```
RawCPR = (RefiCPR + TurnoverCPR)
         × SeasoningMult
         × BurnoutFactor
         × LoanSizeMult
         × GeographyMult
         × CalendarSeasonalityMult
         × PoolSeasonalityFactor

CPR = clamp(RawCPR, TurnoverFloor, MaxCPR)
```
""")

with st.expander("📐 Steps 5-8: SMM, Prepayment, Balance"):
    st.markdown("""
**SMM from CPR:**
```
SMM_t = 1 − (1 − CPR_t)^(1/12)
```

**Unscheduled prepayment:**
```
Prepayment_t = SMM_t × (Balance_{t-1} − SchedPrin_t)
```

**Total principal:**
```
TotalPrincipal_t = SchedPrin_t + Prepayment_t
```

**Ending balance:**
```
Balance_t = Balance_{t-1} − TotalPrincipal_t
```
""")

with st.expander("📐 Steps 9-11: WAL, Duration, Convexity, DV01"):
    st.markdown("""
**Weighted Average Life:**
```
WAL = Σ(t/12 × TotalPrincipal_t) / CurrentBalance   [years]
```

**Price (discounted cash flows):**
```
Price = Σ(TotalCF_t / (1 + r/12)^t) / CurrentBalance × 100
```

**Effective Duration (finite difference):**
```
EffDuration = (Price_dn − Price_up) / (2 × Price_base × Δr)
```
where Δr = 25bp and Price_up/dn are full re-projections at ±Δr.

**Effective Convexity:**
```
Convexity = (Price_dn + Price_up − 2 × Price_base) / (Price_base × Δr²)
```

**DV01:**
```
DV01 = Price_base × EffDuration / 10,000 × FaceValue   [$]
```

**Hedge Ratio (10Y Treasury futures):**
```
HedgeUnits = DV01_pool / DV01_10Y_futures
```
""")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Assumptions
# ─────────────────────────────────────────────────────────────────────────────

section_header("4. Key Assumptions")

st.markdown("""
| Assumption | Value / Approach | Justification |
|---|---|---|
| Discount curve | Flat (single rate) | Simplification; real model uses OAS-adjusted spot curve |
| CPR model type | Rule-based S-curve | No historical calibration; heuristic parameters |
| Burnout | Static input | Real model tracks cumulative prepayment dynamically |
| Servicing fee | Fixed strip | Real pools have tiered servicing |
| Rate scenarios | Parallel + slope only | No swaption vol surface, no curve arbitrage |
| Mortgage rate | Single national rate | No loan-level rate differentiation |
| Seasonality | Fixed calendar multipliers | No dynamic fit to recent data |
| Hedge instrument | 10Y UST futures (stylized DV01) | Real desks use multiple tenors + swaps |
| Pricing | Yield-based (not OAS-based) | No option-adjusted spread computation |
""")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Known Limitations
# ─────────────────────────────────────────────────────────────────────────────

section_header("5. Known Limitations")

st.markdown("""
**Prepayment model:**
- The S-curve CPR model is not empirically calibrated to historical agency data.
  A production model (e.g. Andrew Davidson, Intex, or a proprietary desk model)
  is fit to loan-level or pool-level remittance data using maximum likelihood.

- Burnout is modeled as a static scalar rather than a dynamic state variable
  that tracks cumulative refi activity.  In reality, burnout evolves over time
  as the pool composition shifts.

- No loan-level heterogeneity: the model treats the pool as homogeneous.
  Real pools have distributions of coupons, balances, credit scores, and LTVs
  that generate heterogeneous prepayment behavior.

**Pricing and risk:**
- Price is computed using a flat discount rate, not an OAS-adjusted spot curve.
  This means we are measuring yield-based duration, not option-adjusted duration.
  OAS isolates the spread compensation for prepayment risk.

- No volatility input to the option pricing.  Real MBS duration is
  vol-dependent: higher implied rates volatility → more prepayment optionality →
  shorter effective duration (more negative convexity).

**Scenarios:**
- Rate scenarios assume instantaneous parallel/slope shifts.  Real desks run
  path-dependent scenarios (gradual moves, central bank cycle paths) because
  burnout and seasoning are path-dependent.

**Hedging:**
- A production MBS hedge uses key-rate durations and hedges each bucket
  (2Y, 5Y, 10Y, 30Y) separately with a combination of futures, swaps,
  and swaptions (to address negative convexity).
""")

# ─────────────────────────────────────────────────────────────────────────────
# 6. What I Would Do With Real Data
# ─────────────────────────────────────────────────────────────────────────────

section_header("6. What I Would Do With Real Data")

st.markdown("""
### OAS vs. Yield-Based Duration

The current model prices cash flows using a flat yield (no option adjustment).
With real market data, I would compute the **Option-Adjusted Spread (OAS)**:

1. Build a stochastic short-rate model (e.g. Hull-White, BGM/LMM).
2. Simulate thousands of rate paths.
3. On each path, run the prepayment model to generate path-dependent cash flows.
4. Find the spread OAS such that the average PV across all paths equals the
   market price.

OAS is the "true" spread for MBS after removing the value of the prepayment
option.  It is directly comparable to corporate bond Z-spreads.
OAS duration (also called *option-adjusted duration*) is the correct metric
for hedging and relative value.

---

### Loan-Level vs. Pool-Level Modeling

Agency servicers publish loan-level data (Freddie Mac, Fannie Mae public datasets).
With loan-level data I would:
- Fit separate CPR sub-models by coupon bucket, LTV cohort, FICO band, loan size
- Build a heterogeneous pool model: aggregate loan-level projections into pool-level
- Track burnout dynamically by cohort

---

### Dealer Prepayment Model Services

In practice, MBS desks subscribe to third-party prepayment data and model services:
- **Andrew Davidson & Co. (AD&Co.)** — the industry benchmark prepayment model
- **Intex Solutions** — structured finance cash-flow engine (CMO, ABS, CMBS)
- **Bloomberg MBS Analytics** — integrates dealer models into the terminal
- **CoreLogic / Black Knight** — loan performance, delinquency, and housing data

These services provide:
- Historically calibrated CPR curves by coupon, maturity, and vintage
- Loan-level prepayment forecasts
- CMO tranche cash-flow waterfall decomposition
- TBA pricing and roll analysis

---

### Actual TBA Prices vs. ETF Proxies

This model uses user-defined pool parameters.  In production:
- **TBA (To Be Announced) prices** are the primary MBS market reference
  (Bloomberg MTGE, BGN composite, or dealer runs)
- The TBA market is the most liquid mortgage market (~$300B/day notional)
- **MBS ETFs** (MBB, VMBS) reflect portfolio-level exposure but embed
  management fees and slight tracking error
- Real desks trade specified pools at a premium or discount vs. TBA
  ("pay-up" for specified stories: low loan balance, high LTV, low FICO, NY)

---

### How a Real Desk Would Calibrate the CPR Model

1. **Data:** FNMA/FHLMC monthly remittance files — actual prepayment speeds
   (1-month CPR, 3-month CPR) by pool coupon, vintage, and WALA bucket.

2. **Estimation:** Maximum likelihood estimation (MLE) of the logistic S-curve
   parameters (slope, level, burnout decay rate) against 5+ years of historical
   CPR observations.

3. **Validation:** Out-of-sample R² and RMSE by coupon bucket; check for
   systematic biases in fast/slow prepay periods.

4. **Overrides:** Desk trader overrides for current credit/housing conditions
   (e.g. tighter qualifying standards post-2022 reduce refi sensitivity).

5. **Path dependency:** Run Monte Carlo simulations to capture the fact that
   a pool that has experienced a rate rally already has lower burnout potential
   for the *next* rally.
""")

# ─────────────────────────────────────────────────────────────────────────────
# 7. Model Lineage and References
# ─────────────────────────────────────────────────────────────────────────────

section_header("7. References & Further Reading")

st.markdown("""
- **Fabozzi, F.J. (ed.)** — *The Handbook of Mortgage-Backed Securities* (7th ed.)
  The definitive textbook on MBS analytics, prepayment modeling, and CMO structures.

- **Davidson, A. & Herskovitz, M.** — *Mortgage-Backed Securities: Investment Analysis
  and Advanced Valuation Techniques* — Andrew Davidson's OAS framework.

- **PSA Uniform Practices** — The Public Securities Association (now SIFMA) prepayment
  speed convention (100 PSA = ramp from 0% CPR to 6% CPR over 30 months).

- **FNMA/FHLMC MBS Guides** — Agency seller/servicer guides define pool eligibility,
  g-fee structure, and remittance reporting.

- **Federal Reserve Flow of Funds** — Agency MBS market size and ownership data.
""")

st.divider()
st.caption(
    "Built by Alexander LaPratt · Yale BS CS & Mathematics (4.0 major GPA) · "
    "Prepared for Garda Capital Partners MBS Desk Interview · March 2026"
)
