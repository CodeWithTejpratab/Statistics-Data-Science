"""
Generates synthetic chromatography purification batches, mimicking what
you'd get exporting run logs from a real chromatography skid (e.g. AKTA/
UNICORN), across many production runs. Includes realistic batch-to-batch
noise and resin aging (DBC decay over repeated use cycles) so the dataset
behaves like real process variability rather than a clean toy dataset.

Output: one CSV per batch (curve data) in data/runs/, plus a single
batches.csv with per-batch inputs and summary KPIs.
"""

import os
import numpy as np
import pandas as pd
from thomas_model import thomas_breakthrough, dynamic_binding_capacity, simulate_impurity_curve

RNG = np.random.default_rng(42)

N_BATCHES = 120
N_CYCLES_PER_RESIN_LOT = 30  # resin lots are reused across cycles, then retired
RESIN_LOTS = ["LOT-A", "LOT-B", "LOT-C", "LOT-D"]

OUT_DIR = os.path.join(os.path.dirname(__file__), "data")
RUNS_DIR = os.path.join(OUT_DIR, "runs")
os.makedirs(RUNS_DIR, exist_ok=True)


def resin_capacity_with_aging(q0_fresh, cycle_number, decay_rate=0.006):
    """
    Binding capacity degrades gradually with resin reuse. Simple
    exponential decay is a common simplification for this effect.
    """
    return q0_fresh * np.exp(-decay_rate * cycle_number)


def generate_batches(n_batches=N_BATCHES):
    records = []
    curve_frames = []

    # assign each batch to a resin lot + cycle number, in sequence
    lot_cycle_counters = {lot: 0 for lot in RESIN_LOTS}
    batch_lots = [RESIN_LOTS[i % len(RESIN_LOTS)] for i in range(n_batches)]

    for i, resin_lot in enumerate(batch_lots):
        batch_id = f"BATCH-{i+1:04d}"
        cycle_number = lot_cycle_counters[resin_lot]
        lot_cycle_counters[resin_lot] += 1

        # --- process parameters (with realistic batch-to-batch variability) ---
        q0_fresh = RNG.normal(42.0, 2.0)          # fresh resin capacity, g/L
        q0 = resin_capacity_with_aging(q0_fresh, cycle_number)
        flow_rate = RNG.normal(0.5, 0.05)          # L/min
        feed_titer = RNG.normal(4.5, 0.6)          # g/L
        column_volume = 1.0                        # L, fixed for this scale
        k_th = RNG.normal(0.15, 0.015)
        ph = RNG.normal(7.2, 0.15)
        conductivity = RNG.normal(12.0, 1.0)        # mS/cm

        # pH/conductivity nudge k_th slightly (qualitative process effect)
        k_th_eff = k_th * (1 + 0.02 * (ph - 7.2)) * (1 - 0.01 * (conductivity - 12.0))

        # impurity binds more weakly: lower capacity, faster breakthrough
        q0_imp = q0 * RNG.uniform(0.35, 0.55)
        k_th_imp = k_th_eff * RNG.uniform(1.3, 1.8)
        feed_imp_conc = feed_titer * RNG.uniform(0.05, 0.12)  # impurity load relative to target

        V = np.linspace(0.01, 25, 300)  # throughput volume grid, L

        target_curve = thomas_breakthrough(V, feed_titer, q0, k_th_eff, column_volume, flow_rate)
        impurity_curve = simulate_impurity_curve(V, feed_imp_conc, q0_imp, k_th_imp, column_volume, flow_rate)

        dbc, v_break = dynamic_binding_capacity(V, feed_titer, q0, k_th_eff, column_volume, flow_rate, threshold=0.10)

        # --- derive batch-level KPIs ---
        # load volume: operators vary in how aggressively they load relative to
        # DBC -- some run conservatively under breakthrough, some push past it
        # to squeeze more titer through, which is the real yield-loss lever
        load_ratio = RNG.uniform(0.65, 1.15)
        load_volume = (dbc * column_volume / feed_titer) * load_ratio

        # yield: fraction of target actually captured & eluted
        base_yield = RNG.normal(0.965, 0.008)
        # loading past the breakthrough volume means target molecule is
        # flowing through unbound and lost to the flowthrough -- this is
        # the dominant, physically real driver of yield loss
        overload_penalty = max(0.0, (load_volume - v_break) / v_break) * 1.4 if v_break > 0 else 0
        step_yield = np.clip(base_yield - overload_penalty, 0.5, 0.995) * 100  # percent

        # purity proxy: how much impurity co-elutes relative to target at the load point
        idx_load = np.searchsorted(V, load_volume)
        idx_load = min(idx_load, len(V) - 1)
        imp_breakthrough_frac = impurity_curve[idx_load]
        # higher impurity breakthrough at load point => *better* separation (impurity already washed through)
        # translate to a purity score, noisy
        purity = np.clip(96 + imp_breakthrough_frac * 3 + RNG.normal(0, 0.6), 90, 99.9)

        records.append({
            "batch_id": batch_id,
            "resin_lot": resin_lot,
            "cycle_number": cycle_number,
            "q0_fresh_g_per_L": round(q0_fresh, 2),
            "q0_effective_g_per_L": round(q0, 2),
            "flow_rate_L_per_min": round(flow_rate, 3),
            "feed_titer_g_per_L": round(feed_titer, 2),
            "ph": round(ph, 2),
            "conductivity_mS_cm": round(conductivity, 2),
            "load_volume_L": round(load_volume, 2),
            "dbc_g_per_L_at_10pct": round(dbc, 2),
            "breakthrough_volume_L": round(v_break, 2),
            "step_yield_pct": round(step_yield, 2),
            "purity_pct": round(purity, 2),
        })

        curve_df = pd.DataFrame({
            "batch_id": batch_id,
            "throughput_volume_L": V,
            "target_C_over_C0": target_curve,
            "impurity_C_over_C0": impurity_curve,
        })
        curve_frames.append(curve_df)
        curve_df.to_csv(os.path.join(RUNS_DIR, f"{batch_id}.csv"), index=False)

    batches_df = pd.DataFrame(records)
    batches_df.to_csv(os.path.join(OUT_DIR, "batches.csv"), index=False)

    all_curves_df = pd.concat(curve_frames, ignore_index=True)
    all_curves_df.to_csv(os.path.join(OUT_DIR, "all_run_curves.csv"), index=False)

    return batches_df, all_curves_df


if __name__ == "__main__":
    batches_df, curves_df = generate_batches()
    print(f"Generated {len(batches_df)} batches.")
    print(batches_df.head())
    print(f"\nSaved: {OUT_DIR}/batches.csv")
    print(f"Saved: {OUT_DIR}/all_run_curves.csv")
    print(f"Saved: {len(batches_df)} per-batch curve CSVs in {RUNS_DIR}/")
