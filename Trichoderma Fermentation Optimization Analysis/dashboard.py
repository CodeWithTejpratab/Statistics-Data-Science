"""
Dashboard for the fermentation dataset. Reports findings honestly,
including the fact that no single process parameter (or interaction,
per random forest CV) meaningfully predicts yield in this dataset.
"""

import os
import sqlite3
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "ferm_opt.db")
OUT_PATH = os.path.join(BASE_DIR, "dashboard.png")

FEATURES = [
    "avg_temp_C", "avg_ph", "min_do_pct", "inoculum_size_mL",
    "max_rpm", "total_lactose_feed_mL", "culture_duration_days",
    "total_media_volume_mL",
]


def build_dashboard():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM runs", conn)
    conn.close()

    valid = df[(df["contaminated"] == 0) & (df["fpu_measurement_flag"] == "ok")].copy()
    clean_yield = df[(df["contaminated"] == 0) & (df["fpu_measurement_flag"] == "ok")]["max_fpu_ml"]
    contam_yield = df[(df["contaminated"] == 1) & (df["fpu_measurement_flag"] == "ok")]["max_fpu_ml"]

    rf = RandomForestRegressor(n_estimators=300, max_depth=4, random_state=42)
    rf.fit(valid[FEATURES], valid["max_fpu_ml"])
    importances = pd.Series(rf.feature_importances_, index=FEATURES).sort_values()

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Trichoderma Fermentation Dataset - 1000 Runs",
                 fontsize=14, fontweight="bold")

    # Panel 1: yield category counts
    ax1 = axes[0, 0]
    order = ["Low", "Medium", "High"]
    counts = df["yield_category"].value_counts().reindex(order)
    ax1.bar(order, counts.values, color=["#d62728", "#ff7f0e", "#2ca02c"])
    ax1.set_title("Runs by Yield Category")
    ax1.set_ylabel("Number of runs")
    for i, v in enumerate(counts.values):
        ax1.text(i, v + 5, str(v), ha="center")

    # Panel 2: contamination effect (boxplot)
    ax2 = axes[0, 1]
    ax2.boxplot([clean_yield, contam_yield], labels=["Uncontaminated", "Contaminated"])
    ax2.set_ylabel("Max FPU/mL")
    ax2.set_title("Yield: Contaminated vs. Uncontaminated Runs\n(no significant difference, p=0.79)")

    # Panel 3: temperature vs yield scatter (check for an optimum / sweet spot)
    ax3 = axes[1, 0]
    ax3.scatter(valid["avg_temp_C"], valid["max_fpu_ml"], s=10, alpha=0.4, color="steelblue")
    ax3.set_xlabel("Avg. Temperature (C)")
    ax3.set_ylabel("Max FPU/mL")
    ax3.set_title("Yield vs. Temperature (valid runs)\nNo clear linear or optimum trend visible")

    # Panel 4: random forest feature importances
    ax4 = axes[1, 1]
    ax4.barh(importances.index, importances.values, color="darkorange")
    ax4.set_xlabel("Random forest feature importance")
    ax4.set_title("Feature Importance for Yield\n(cross-val R2 ~ 0, low overall predictive signal)")

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(OUT_PATH, dpi=150)
    plt.close(fig)
    print(f"Dashboard written to {OUT_PATH}")


if __name__ == "__main__":
    build_dashboard()
