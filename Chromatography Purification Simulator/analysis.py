"""
Statistical analysis layer.

1. Multiple linear regression: which process inputs most affect step yield
   and DBC.
2. Resin decay model: fit DBC vs. cycle number per resin lot, and flag when
   a lot crosses an end-of-life threshold.
3. A simple factorial "DoE-style" effects summary using the generated data
   (standardized regression coefficients as a stand-in for main effects).
"""

import os
import sqlite3
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "chrom_sim.db")

FEATURES = [
    "q0_effective_g_per_L", "flow_rate_L_per_min", "feed_titer_g_per_L",
    "ph", "conductivity_mS_cm", "load_volume_L", "cycle_number",
]


def load_joined():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        """
        SELECT b.*, k.dbc_g_per_L_at_10pct, k.breakthrough_volume_L,
               k.step_yield_pct, k.purity_pct
        FROM batches b JOIN kpis k ON b.batch_id = k.batch_id
        """,
        conn,
    )
    conn.close()
    return df


def regression_effects(df, target_col):
    """Standardized regression coefficients = comparable 'effect sizes'."""
    X = df[FEATURES].values
    y = df[target_col].values

    scaler_X = StandardScaler()
    X_std = scaler_X.fit_transform(X)
    y_std = (y - y.mean()) / y.std()

    model = LinearRegression().fit(X_std, y_std)
    effects = pd.Series(model.coef_, index=FEATURES).sort_values(key=abs, ascending=False)
    r2 = model.score(X_std, y_std)
    return effects, r2


def resin_decay_fit(df, eol_threshold_g_per_L=28.0):
    """
    Fit DBC vs cycle_number per resin lot (simple linear fit is enough to
    show the trend); report the cycle number at which each lot is
    projected to cross the end-of-life threshold.
    """
    results = []
    for lot, g in df.groupby("resin_lot"):
        g = g.sort_values("cycle_number")
        coeffs = np.polyfit(g["cycle_number"], g["dbc_g_per_L_at_10pct"], deg=1)
        slope, intercept = coeffs
        if slope < 0:
            cycle_at_eol = (eol_threshold_g_per_L - intercept) / slope
        else:
            cycle_at_eol = float("inf")
        results.append({
            "resin_lot": lot,
            "dbc_slope_per_cycle": round(slope, 3),
            "dbc_intercept": round(intercept, 2),
            "projected_eol_cycle": round(cycle_at_eol, 1) if np.isfinite(cycle_at_eol) else None,
            "cycles_observed": len(g),
        })
    return pd.DataFrame(results)


def run_analysis():
    df = load_joined()

    yield_effects, yield_r2 = regression_effects(df, "step_yield_pct")
    dbc_effects, dbc_r2 = regression_effects(df, "dbc_g_per_L_at_10pct")
    decay_df = resin_decay_fit(df)

    print("=" * 60)
    print("STEP YIELD — standardized effect sizes (R^2 = {:.2f})".format(yield_r2))
    print("=" * 60)
    print(yield_effects.to_string())

    print()
    print("=" * 60)
    print("DYNAMIC BINDING CAPACITY (DBC) — standardized effect sizes (R^2 = {:.2f})".format(dbc_r2))
    print("=" * 60)
    print(dbc_effects.to_string())

    print()
    print("=" * 60)
    print("RESIN AGING — DBC decay per lot & projected end-of-life cycle")
    print("=" * 60)
    print(decay_df.to_string(index=False))

    return {
        "yield_effects": yield_effects,
        "yield_r2": yield_r2,
        "dbc_effects": dbc_effects,
        "dbc_r2": dbc_r2,
        "decay_df": decay_df,
        "df": df,
    }


if __name__ == "__main__":
    run_analysis()
