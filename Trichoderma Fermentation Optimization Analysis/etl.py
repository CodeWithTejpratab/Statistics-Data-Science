"""
Loads the cleaned fermentation dataset into a small SQLite database.
Single-table here (the raw data is already batch-level, unlike the
purification simulator which had per-timepoint curve data too) --
but still real data modeling: explicit types, a documented schema,
and a view for the "valid" runs used in yield modeling.
"""

import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(__file__)
CLEAN_PATH = os.path.join(BASE_DIR, "data", "clean_runs.csv")
DB_PATH = os.path.join(BASE_DIR, "ferm_opt.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    avg_temp_C REAL,
    avg_ph REAL,
    min_do_pct REAL,
    inoculum_size_mL REAL,
    max_rpm REAL,
    total_lactose_feed_mL REAL,
    culture_duration_days REAL,
    contaminated INTEGER,
    total_media_volume_mL REAL,
    max_fpu_ml REAL,
    max_fpu_ml_raw REAL,
    fpu_measurement_flag TEXT,
    yield_category TEXT
);

-- runs with no contamination and no negative-yield flag: the "clean"
-- subset for modeling process-parameter effects on yield without
-- contamination or assay-noise confounds
CREATE VIEW IF NOT EXISTS runs_valid AS
SELECT * FROM runs
WHERE contaminated = 0 AND fpu_measurement_flag = 'ok';
"""


def build_database():
    df = pd.read_csv(CLEAN_PATH)
    df["contaminated"] = df["contaminated"].astype(int)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    df.to_sql("runs", conn, if_exists="append", index=False)
    conn.commit()

    check = pd.read_sql("SELECT COUNT(*) AS n_valid_runs FROM runs_valid", conn)
    conn.close()
    return check


if __name__ == "__main__":
    result = build_database()
    print(f"Database built at {DB_PATH}")
    print(result)
