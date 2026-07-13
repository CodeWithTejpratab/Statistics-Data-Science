"""
ETL: loads the synthetic batch + curve CSVs into a small SQLite database
with a normalized schema. This is the "data modeling and database design"
piece of the project — a real relational structure rather than one flat
CSV, so downstream queries and dashboards can join across it.

Schema:
    batches      -- one row per batch: process inputs
    run_curves   -- one row per (batch, throughput volume) point: raw breakthrough data
    kpis         -- one row per batch: derived outputs (yield, purity, DBC)
"""

import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(BASE_DIR, "chrom_sim.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    resin_lot TEXT NOT NULL,
    cycle_number INTEGER NOT NULL,
    q0_fresh_g_per_L REAL,
    q0_effective_g_per_L REAL,
    flow_rate_L_per_min REAL,
    feed_titer_g_per_L REAL,
    ph REAL,
    conductivity_mS_cm REAL,
    load_volume_L REAL
);

CREATE TABLE IF NOT EXISTS run_curves (
    batch_id TEXT NOT NULL,
    throughput_volume_L REAL NOT NULL,
    target_C_over_C0 REAL,
    impurity_C_over_C0 REAL,
    FOREIGN KEY (batch_id) REFERENCES batches(batch_id)
);

CREATE TABLE IF NOT EXISTS kpis (
    batch_id TEXT PRIMARY KEY,
    dbc_g_per_L_at_10pct REAL,
    breakthrough_volume_L REAL,
    step_yield_pct REAL,
    purity_pct REAL,
    FOREIGN KEY (batch_id) REFERENCES batches(batch_id)
);
"""

BATCH_COLS = [
    "batch_id", "resin_lot", "cycle_number", "q0_fresh_g_per_L",
    "q0_effective_g_per_L", "flow_rate_L_per_min", "feed_titer_g_per_L",
    "ph", "conductivity_mS_cm", "load_volume_L",
]
KPI_COLS = [
    "batch_id", "dbc_g_per_L_at_10pct", "breakthrough_volume_L",
    "step_yield_pct", "purity_pct",
]


def build_database():
    batches_df = pd.read_csv(os.path.join(DATA_DIR, "batches.csv"))
    curves_df = pd.read_csv(os.path.join(DATA_DIR, "all_run_curves.csv"))

    # fresh DB each run, so this script is idempotent
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    batches_df[BATCH_COLS].to_sql("batches", conn, if_exists="append", index=False)
    curves_df.to_sql("run_curves", conn, if_exists="append", index=False)
    batches_df[KPI_COLS].to_sql("kpis", conn, if_exists="append", index=False)

    conn.commit()

    # sanity check: a join across all three tables
    check = pd.read_sql(
        """
        SELECT b.batch_id, b.resin_lot, b.cycle_number, k.step_yield_pct, k.purity_pct
        FROM batches b
        JOIN kpis k ON b.batch_id = k.batch_id
        ORDER BY b.batch_id
        LIMIT 5
        """,
        conn,
    )
    conn.close()
    return check


if __name__ == "__main__":
    result = build_database()
    print(f"Database built at {DB_PATH}")
    print(result)
