"""
ingest_fannie_mae.py — Fannie Mae Single-Family Loan Performance Data ingestion.

Reads a raw pipe-delimited FNMA SFLP quarterly file (no header row), assigns
column names, cleans the data, groups loans into WAC buckets, and writes a
pool-profile CSV that the dashboard can load directly.

Usage:
    python -m src.ingest_fannie_mae                          # uses default path
    python -m src.ingest_fannie_mae --input path/to/file.csv # custom path

Output:
    data/processed/fannie_mae_pool_profiles.csv
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=pd.errors.DtypeWarning)

# ---------------------------------------------------------------------------
# Column schema
# ---------------------------------------------------------------------------
# Fannie Mae SFLP files have no header.  The file begins with a leading pipe
# so position 0 is always empty.  We assign the 41 user-specified names to
# positions 1-41 and generic COL_N names for the remaining fields.

_NAMED_COLS = [
    "LOAN_ID",
    "ORIG_DATE",
    "CHANNEL",
    "SELLER_NAME",
    "SERVICER_NAME",
    "MASTER_SERVICER",
    "ORIG_INTEREST_RATE",
    "CURRENT_INTEREST_RATE",
    "ORIG_UPB",
    "CURRENT_UPB",
    "ORIG_LOAN_TERM",
    "ORIG_DATE_2",
    "FIRST_PAYMENT_DATE",
    "MATURITY_DATE",
    "LOAN_AGE",
    "REMAINING_MONTHS",
    "ADJUSTED_MONTHS",
    "MSA",
    "ORIG_LTV",
    "ORIG_CLTV",
    "NUMBER_OF_BORROWERS",
    "DTI",
    "CREDIT_SCORE_1",
    "CREDIT_SCORE_2",
    "FIRST_TIME_BUYER",
    "LOAN_PURPOSE",
    "PROPERTY_TYPE",
    "NUMBER_OF_UNITS",
    "OCCUPANCY",
    "PROPERTY_STATE",
    "ZIP_CODE",
    "MI_PCT",
    "PRODUCT_TYPE",
    "AMORTIZATION_TYPE",
    "PREPAY_PENALTY",
    "IO_FLAG",
    "EXTRA_1",
    "EXTRA_2",
    "EXTRA_3",
    "LOAN_SEQUENCE",
    "HIGH_BALANCE_FLAG",
]

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INPUT = (
    _REPO_ROOT.parent / "archive" / "2024Q1.csv"
)
_DEFAULT_OUTPUT = _REPO_ROOT / "data" / "processed" / "fannie_mae_pool_profiles.csv"

# Rate bucket definitions: (label, low_inclusive, high_exclusive)
_RATE_BUCKETS = [
    ("3-4%",  3.0,  4.0),
    ("4-5%",  4.0,  5.0),
    ("5-6%",  5.0,  6.0),
    ("6-7%",  6.0,  7.0),
    ("7%+",   7.0, 99.0),
]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _build_column_names(n_total: int) -> list[str]:
    """
    Build a list of n_total column names.
    Position 0 = '_LEADING_PIPE' (always empty due to leading | in file).
    Positions 1-41 = _NAMED_COLS.
    Positions 42+ = COL_42, COL_43, …
    """
    cols: list[str] = ["_LEADING_PIPE"]
    cols.extend(_NAMED_COLS)
    for i in range(len(_NAMED_COLS) + 1, n_total):
        cols.append(f"COL_{i + 1}")
    return cols


def read_raw(input_path: str | Path) -> pd.DataFrame:
    """
    Read the pipe-delimited FNMA file and assign column names.

    NOTE on column offset: In the actual 2024Q1 SFLP file, field [11] holds
    the current-period UPB and field [12] holds the origination loan term (360).
    The user-supplied label 'ORIG_LOAN_TERM' falls on field [11] and
    'ORIG_DATE_2' falls on field [12].  We correct this after reading by
    swapping those two labels so that ORIG_LOAN_TERM == 360 and LOAN_AGE
    remains correctly positioned at field [15].
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    print(f"Reading {input_path} …")

    # Peek at first row to count columns
    with open(input_path, "r", encoding="utf-8", errors="replace") as fh:
        first_line = fh.readline().rstrip("\n")
    n_cols = len(first_line.split("|"))

    col_names = _build_column_names(n_cols)

    df = pd.read_csv(
        input_path,
        sep="|",
        header=None,
        names=col_names,
        dtype=str,
        low_memory=False,
    )

    # Fix the label swap: what is labeled ORIG_LOAN_TERM is actually
    # current-period UPB; what is labeled ORIG_DATE_2 is the actual term (360).
    df = df.rename(columns={
        "ORIG_LOAN_TERM": "CURRENT_ACTUAL_UPB",
        "ORIG_DATE_2":    "ORIG_LOAN_TERM",
    })

    print(f"  Raw rows read : {len(df):,}")
    print(f"  Columns       : {n_cols}")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and filter the raw DataFrame.

    Steps:
    1. Coerce numeric columns to float/int.
    2. Drop rows with null ORIG_INTEREST_RATE, ORIG_UPB, or ORIG_LOAN_TERM.
    3. Keep only 30-year fixed (ORIG_LOAN_TERM == 360).
    4. Remove loans with ORIG_INTEREST_RATE outside [2.0, 12.0].
    5. Remove loans with ORIG_UPB <= 0.
    6. Keep only origination records (LOAN_AGE == 0 or -1) to avoid double-
       counting the same loan across multiple monthly performance observations.
    """
    numeric_cols = {
        "ORIG_INTEREST_RATE": float,
        "CURRENT_INTEREST_RATE": float,
        "ORIG_UPB": float,
        "CURRENT_UPB": float,
        "ORIG_LOAN_TERM": float,
        "LOAN_AGE": float,
        "ORIG_LTV": float,
        "ORIG_CLTV": float,
        "DTI": float,
        "CREDIT_SCORE_1": float,
        "CREDIT_SCORE_2": float,
        "NUMBER_OF_BORROWERS": float,
        "MI_PCT": float,
    }
    for col, dtype in numeric_cols.items():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Drop required-field nulls ---
    required = ["ORIG_INTEREST_RATE", "ORIG_UPB", "ORIG_LOAN_TERM"]
    before = len(df)
    df = df.dropna(subset=required)
    print(f"  After dropping null required fields : {len(df):,}  (removed {before - len(df):,})")

    # --- Keep only origination records (LOAN_AGE in {-1, 0, 1}) ---
    # FNMA SFLP files can contain many monthly updates for the same loan.
    # We keep only the first observation (loan age 0 or -1) to get one
    # row per loan at origination.
    if "LOAN_AGE" in df.columns:
        before = len(df)
        df = df[df["LOAN_AGE"].isin([-1.0, 0.0, 1.0])]
        print(f"  After keeping origination records   : {len(df):,}  (removed {before - len(df):,})")

    # --- 30-year fixed only ---
    before = len(df)
    df = df[df["ORIG_LOAN_TERM"] == 360.0]
    print(f"  After WAM==360 filter               : {len(df):,}  (removed {before - len(df):,})")

    # --- Rate range filter ---
    before = len(df)
    df = df[(df["ORIG_INTEREST_RATE"] >= 2.0) & (df["ORIG_INTEREST_RATE"] <= 12.0)]
    print(f"  After rate [2-12%] filter           : {len(df):,}  (removed {before - len(df):,})")

    # --- Positive balance ---
    before = len(df)
    df = df[df["ORIG_UPB"] > 0]
    print(f"  After ORIG_UPB > 0 filter           : {len(df):,}  (removed {before - len(df):,})")

    return df.reset_index(drop=True)


def assign_rate_bucket(df: pd.DataFrame) -> pd.DataFrame:
    """Add a RATE_BUCKET column based on ORIG_INTEREST_RATE."""
    conditions = []
    labels = []
    for label, lo, hi in _RATE_BUCKETS:
        conditions.append((df["ORIG_INTEREST_RATE"] >= lo) & (df["ORIG_INTEREST_RATE"] < hi))
        labels.append(label)
    df = df.copy()
    df["RATE_BUCKET"] = np.select(conditions, labels, default="other")
    return df


def compute_pool_profiles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Group by RATE_BUCKET and compute pool-level aggregates.

    Returns one row per bucket with columns the dashboard uses directly
    to pre-populate WAC, WAM, balance sliders, and informational stats.
    """
    rows = []
    bucket_order = [b[0] for b in _RATE_BUCKETS]

    for bucket in bucket_order:
        grp = df[df["RATE_BUCKET"] == bucket]
        if grp.empty:
            continue

        total_upb = grp["ORIG_UPB"].sum()
        wac = (grp["ORIG_INTEREST_RATE"] * grp["ORIG_UPB"]).sum() / total_upb
        avg_ltv = grp["ORIG_LTV"].mean() if "ORIG_LTV" in grp else np.nan
        avg_cltv = grp["ORIG_CLTV"].mean() if "ORIG_CLTV" in grp else np.nan
        avg_dti = grp["DTI"].mean() if "DTI" in grp else np.nan
        avg_fico = grp["CREDIT_SCORE_1"].mean() if "CREDIT_SCORE_1" in grp else np.nan
        avg_loan_size = grp["ORIG_UPB"].mean()
        loan_count = len(grp)

        top_state = (
            grp["PROPERTY_STATE"].value_counts().idxmax()
            if "PROPERTY_STATE" in grp.columns and not grp["PROPERTY_STATE"].isna().all()
            else "N/A"
        )

        rows.append({
            "rate_bucket":    bucket,
            "wac":            round(wac, 4),
            "wam":            360,
            "avg_ltv":        round(avg_ltv, 2) if not np.isnan(avg_ltv) else None,
            "avg_cltv":       round(avg_cltv, 2) if not np.isnan(avg_cltv) else None,
            "avg_dti":        round(avg_dti, 2) if not np.isnan(avg_dti) else None,
            "avg_fico":       round(avg_fico, 1) if not np.isnan(avg_fico) else None,
            "avg_loan_size":  round(avg_loan_size, 2),
            "total_balance":  round(total_upb, 2),
            "loan_count":     loan_count,
            "top_state":      top_state,
        })

    return pd.DataFrame(rows)


def print_summary(profiles: pd.DataFrame) -> None:
    """Pretty-print the pool profile summary to stdout."""
    print("\n" + "=" * 72)
    print("  FANNIE MAE 2024 Q1 — POOL PROFILES BY RATE BUCKET")
    print("=" * 72)
    print(f"  {'Bucket':<8} {'Loans':>8} {'WAC':>7} {'Avg Loan $':>12} "
          f"{'Avg LTV':>8} {'Avg FICO':>9} {'Total Bal $B':>13} {'Top State':>10}")
    print("  " + "-" * 70)
    for _, row in profiles.iterrows():
        total_b = row["total_balance"] / 1e9
        avg_loan = row["avg_loan_size"] / 1e3
        fico = f"{row['avg_fico']:.0f}" if row["avg_fico"] else "N/A"
        ltv = f"{row['avg_ltv']:.1f}%" if row["avg_ltv"] else "N/A"
        print(
            f"  {row['rate_bucket']:<8} "
            f"{row['loan_count']:>8,} "
            f"{row['wac']:>6.3f}% "
            f"${avg_loan:>10.1f}K "
            f"{ltv:>8} "
            f"{fico:>9} "
            f"${total_b:>11.2f}B "
            f"{row['top_state']:>10}"
        )
    print("=" * 72)
    total_loans = profiles["loan_count"].sum()
    total_bal = profiles["total_balance"].sum() / 1e9
    print(f"  TOTAL: {total_loans:,} loans  |  ${total_bal:.2f}B original balance")
    print("=" * 72 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(input_path: str | Path | None = None, output_path: str | Path | None = None) -> pd.DataFrame:
    input_path  = Path(input_path)  if input_path  else _DEFAULT_INPUT
    output_path = Path(output_path) if output_path else _DEFAULT_OUTPUT

    output_path.parent.mkdir(parents=True, exist_ok=True)

    df_raw      = read_raw(input_path)
    df_clean    = clean(df_raw)
    df_bucketed = assign_rate_bucket(df_clean)
    profiles    = compute_pool_profiles(df_bucketed)

    profiles.to_csv(output_path, index=False)
    print(f"\nPool profiles saved → {output_path}")

    print_summary(profiles)
    return profiles


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Fannie Mae SFLP CSV into pool profiles.")
    parser.add_argument("--input",  type=str, default=None, help="Path to raw 2024Q1.csv")
    parser.add_argument("--output", type=str, default=None, help="Output CSV path")
    args = parser.parse_args()
    main(args.input, args.output)
