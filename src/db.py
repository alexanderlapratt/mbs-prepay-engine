"""
db.py — Database initialization, connection management, and persistence helpers.

Uses SQLite via SQLAlchemy for portability and ease of deployment to Streamlit
Community Cloud (no external database service required).

Functions:
  - init_db()         Initialize the schema and seed data
  - get_engine()      Return a SQLAlchemy engine (cached singleton)
  - save_run()        Persist a completed model run to the database
  - load_scenarios()  Load scenario definitions from the DB
  - load_pool()       Load pool static data by pool_id
"""

from __future__ import annotations

import sqlite3
import os
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.config import DB_PATH, SQL_DIR, DATABASE_URL


# ---------------------------------------------------------------------------
# Engine (singleton per process)
# ---------------------------------------------------------------------------

_engine: Optional[Engine] = None


def get_engine() -> Engine:
    """
    Return the SQLAlchemy engine, creating it on first call.

    Using a module-level singleton ensures we don't create a new connection
    pool on every Streamlit re-run.
    """
    global _engine
    if _engine is None:
        _engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return _engine


# ---------------------------------------------------------------------------
# Schema and seed initialization
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Initialize the SQLite database: create tables (schema.sql) and load seed
    data (seed.sql) if not already present.

    Safe to call multiple times — uses CREATE IF NOT EXISTS and INSERT OR IGNORE.
    Called once at Streamlit app startup.
    """
    schema_path = SQL_DIR / "schema.sql"
    seed_path   = SQL_DIR / "seed.sql"
    views_path  = SQL_DIR / "views.sql"

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    for sql_file in [schema_path, seed_path, views_path]:
        if sql_file.exists():
            sql_text = sql_file.read_text()
            # SQLite executescript handles multi-statement files
            conn.executescript(sql_text)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_scenarios() -> pd.DataFrame:
    """
    Load all scenario definitions from the database.

    Returns a DataFrame with columns matching scenario_definitions table.
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql("SELECT * FROM scenario_definitions ORDER BY scenario_id", conn)


def load_pool(pool_id: str = "FNMA_30Y_6PCT") -> Optional[dict]:
    """
    Load pool static data for a given pool_id.

    Returns a dict with pool attributes or None if not found.
    Useful for pre-populating the Pool Setup page with the seed pool.

    Args:
        pool_id: Primary key from pool_static table.

    Returns:
        Dict of pool attributes or None.
    """
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM pool_static WHERE pool_id = :pid"),
            {"pid": pool_id},
        ).mappings().first()
    return dict(result) if result else None


def load_rate_history() -> pd.DataFrame:
    """
    Load interest rate history sorted by date.

    Returns a DataFrame with the benchmark rate time series.
    Used to display the rate context chart on the Pool Setup page.
    """
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(
            "SELECT * FROM rate_history ORDER BY as_of_date",
            conn,
        )


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def save_run(
    pool_id:        str,
    discount_rate:  float,
    num_scenarios:  int,
    scenario_results: list[dict],
) -> int:
    """
    Persist a completed scenario run to the database.

    Inserts a model_runs header row and then saves projected_cashflows and
    risk_results for every scenario.

    Args:
        pool_id:          Pool identifier.
        discount_rate:    Base discount rate used.
        num_scenarios:    Number of scenarios run.
        scenario_results: Output of scenario_engine.run_all_scenarios().

    Returns:
        run_id of the inserted record.
    """
    engine  = get_engine()
    conn    = sqlite3.connect(str(DB_PATH))

    try:
        # Insert model run header
        cur = conn.execute(
            """
            INSERT INTO model_runs (pool_id, discount_rate, num_scenarios, status)
            VALUES (?, ?, ?, 'complete')
            """,
            (pool_id, discount_rate, num_scenarios),
        )
        run_id = cur.lastrowid

        # Fetch scenario IDs from DB
        rows = conn.execute("SELECT scenario_id, scenario_name FROM scenario_definitions").fetchall()
        scenario_id_map = {name: sid for sid, name in rows}

        for result in scenario_results:
            scenario_name = result["scenario_name"]
            scenario_id   = scenario_id_map.get(scenario_name)
            if scenario_id is None:
                continue

            # Save risk results
            conn.execute(
                """
                INSERT OR REPLACE INTO risk_results
                    (run_id, pool_id, scenario_id, wal, price, eff_duration, convexity, dv01, hedge_units)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id, pool_id, scenario_id,
                    result.get("wal"), result.get("price"),
                    result.get("eff_duration"), result.get("convexity"),
                    result.get("dv01"), result.get("hedge_units"),
                ),
            )

            # Save projected cash flows (limit to first 120 months to keep DB small)
            cfs = result.get("cashflows", [])[:120]
            for cf in cfs:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO projected_cashflows
                        (run_id, pool_id, scenario_id, period, beginning_balance,
                         scheduled_payment, interest, scheduled_principal,
                         cpr, smm, prepayment, total_principal, ending_balance, total_cashflow)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id, pool_id, scenario_id,
                        cf["period"], cf["beginning_balance"],
                        cf["scheduled_payment"], cf["interest"],
                        cf["scheduled_principal"], cf["cpr"], cf["smm"],
                        cf["prepayment"], cf["total_principal"],
                        cf["ending_balance"], cf["total_cashflow"],
                    ),
                )

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

    return run_id


def load_latest_risk_results(pool_id: str = "FNMA_30Y_6PCT") -> pd.DataFrame:
    """
    Load the most recent risk results for a pool from the DB.

    Returns a DataFrame joining risk_results, scenario_definitions, and
    pool_static for display on the Risk page.
    """
    engine = get_engine()
    with engine.connect() as conn:
        try:
            return pd.read_sql(
                """
                SELECT * FROM v_risk_summary
                WHERE pool_id = :pid
                ORDER BY scenario_id
                """,
                conn,
                params={"pid": pool_id},
            )
        except Exception:
            return pd.DataFrame()
