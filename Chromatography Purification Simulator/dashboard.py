"""
Builds a single static dashboard image (matplotlib, fully offline) covering:
  1. Batch-over-batch yield & purity trends
  2. DBC decay per resin lot, with end-of-life threshold line
  3. Standardized effect sizes (yield drivers, DBC drivers)
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis import run_analysis

OUT_PATH = os.path.join(os.path.dirname(__file__), "dashboard.png")
EOL_THRESHOLD = 28.0


def build_dashboard():
    results = run_analysis()
    df = results["df"]
    decay_df = results["decay_df"]
    yield_effects = results["yield_effects"]
    dbc_effects = results["dbc_effects"]

    df_sorted = df.sort_values("batch_id").reset_index(drop=True)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Chromatography Purification Process Dashboard - 120 Simulated Batches",
                 fontsize=14, fontweight="bold")

    ax1 = axes[0, 0]
    ax1b = ax1.twinx()
    x = range(len(df_sorted))
    ax1.plot(x, df_sorted["step_yield_pct"], color="steelblue", marker="o", markersize=2,
             linewidth=1, label="Step Yield (%)")
    ax1b.plot(x, df_sorted["purity_pct"], color="darkorange", marker="o", markersize=2,
              linewidth=1, linestyle="--", label="Purity (%)")
    ax1.set_ylabel("Step Yield (%)", color="steelblue")
    ax1b.set_ylabel("Purity (%)", color="darkorange")
    ax1.set_xlabel("Batch sequence")
    ax1.set_title("Step Yield & Purity by Batch")
    ax1.tick_params(axis="x", labelbottom=False)
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax1b.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="lower left", fontsize=8)

    ax2 = axes[0, 1]
    for lot, g in df.groupby("resin_lot"):
        g = g.sort_values("cycle_number")
        ax2.scatter(g["cycle_number"], g["dbc_g_per_L_at_10pct"], s=20, label=lot)
    max_cycle = df["cycle_number"].max()
    ax2.plot([0, max_cycle], [EOL_THRESHOLD, EOL_THRESHOLD], color="red",
             linestyle="--", label="EOL threshold")
    ax2.set_xlabel("Cycle number")
    ax2.set_ylabel("DBC (g/L, 10% breakthrough)")
    ax2.set_title("Dynamic Binding Capacity Decay by Resin Lot")
    ax2.legend(fontsize=8)

    ax3 = axes[1, 0]
    ax3.barh(yield_effects.index, yield_effects.values, color="steelblue")
    ax3.set_xlabel("Standardized coefficient")
    ax3.set_title("Standardized Effects - Step Yield (R2 = {:.2f})".format(results["yield_r2"]))
    ax3.axvline(0, color="black", linewidth=0.8)

    ax4 = axes[1, 1]
    ax4.barh(dbc_effects.index, dbc_effects.values, color="darkorange")
    ax4.set_xlabel("Standardized coefficient")
    ax4.set_title("Standardized Effects - DBC (R2 = {:.2f})".format(results["dbc_r2"]))
    ax4.axvline(0, color="black", linewidth=0.8)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(OUT_PATH, dpi=150)
    plt.close(fig)

    print("Resin lot end-of-life projections (cycle number):")
    print(decay_df[["resin_lot", "projected_eol_cycle", "cycles_observed"]].to_string(index=False))
    print("\nDashboard written to: " + OUT_PATH)


if __name__ == "__main__":
    build_dashboard()
