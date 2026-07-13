"""
Statistical analysis of the fermentation dataset.

1. Quantify the impact of contamination on yield (a real, large effect
   in this dataset -- 43% of runs are contaminated).
2. Among valid (uncontaminated, non-negative-flagged) runs, regress
   Max FPU/mL on process parameters to find the real yield drivers.
"""

import os
import sqlite3
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from scipy import stats

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "ferm_opt.db")

FEATURES = [
    "avg_temp_C", "avg_ph", "min_do_pct", "inoculum_size_mL",
    "max_rpm", "total_lactose_feed_mL", "culture_duration_days",
    "total_media_volume_mL",
]


def load_all():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM runs", conn)
    conn.close()
    return df


def contamination_effect(df):
    clean_runs = df[(df["contaminated"] == 0) & (df["fpu_measurement_flag"] == "ok")]
    contam_runs = df[(df["contaminated"] == 1) & (df["fpu_measurement_flag"] == "ok")]

    mean_clean = clean_runs["max_fpu_ml"].mean()
    mean_contam = contam_runs["max_fpu_ml"].mean()
    t_stat, p_val = stats.ttest_ind(clean_runs["max_fpu_ml"], contam_runs["max_fpu_ml"], equal_var=False)

    return {
        "n_clean": len(clean_runs),
        "n_contaminated": len(contam_runs),
        "mean_fpu_clean": round(mean_clean, 3),
        "mean_fpu_contaminated": round(mean_contam, 3),
        "pct_yield_loss_from_contamination": round(100 * (mean_clean - mean_contam) / mean_clean, 1),
        "t_stat": round(t_stat, 2),
        "p_value": p_val,
    }


def yield_driver_regression(df):
    valid = df[(df["contaminated"] == 0) & (df["fpu_measurement_flag"] == "ok")].copy()

    X = valid[FEATURES].values
    y = valid["max_fpu_ml"].values

    scaler = StandardScaler()
    X_std = scaler.fit_transform(X)
    y_std = (y - y.mean()) / y.std()

    model = LinearRegression().fit(X_std, y_std)
    effects = pd.Series(model.coef_, index=FEATURES).sort_values(key=abs, ascending=False)
    r2 = model.score(X_std, y_std)
    return effects, r2, valid


def run_analysis():
    df = load_all()
    contam_stats = contamination_effect(df)
    effects, r2, valid_df = yield_driver_regression(df)

    print("=" * 60)
    print("CONTAMINATION IMPACT ON YIELD")
    print("=" * 60)
    for k, v in contam_stats.items():
        print(f"  {k}: {v}")

    print()
    print("=" * 60)
    print(f"YIELD DRIVERS (valid runs only, n={len(valid_df)}) -- standardized effects (R^2={r2:.2f})")
    print("=" * 60)
    print(effects.to_string())

    return {"contam_stats": contam_stats, "effects": effects, "r2": r2, "df": df, "valid_df": valid_df}


if __name__ == "__main__":
    run_analysis()
