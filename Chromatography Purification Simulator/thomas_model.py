"""
Thomas model for chromatography breakthrough curves.

The Thomas model is a classic analytical solution used to describe
fixed-bed adsorption (e.g. Protein A capture chromatography). It gives
the ratio of outlet to feed concentration (C/C0) as a function of
cumulative throughput volume.

    C/C0 = 1 / (1 + exp[(k_Th * q0 * m - k_Th * C0 * V) / Q])

where:
    C      = effluent (outlet) concentration
    C0     = feed concentration
    q0     = maximum binding capacity of the resin (mass target / volume resin)
    k_Th   = Thomas rate constant
    m      = resin volume (column volume, CV)
    V      = cumulative throughput volume
    Q      = volumetric flow rate
"""

import numpy as np


def thomas_breakthrough(V, C0, q0, k_th, m, Q):
    """
    Compute C/C0 at given throughput volumes V.

    Parameters
    ----------
    V : array-like
        Cumulative throughput volume (L), one or more points.
    C0 : float
        Feed concentration (g/L).
    q0 : float
        Maximum binding capacity (g/L resin).
    k_th : float
        Thomas rate constant (L / (g * min)-ish units; treated as an
        empirical tuning constant here, not unit-strict).
    m : float
        Resin volume (L).
    Q : float
        Flow rate (L/min).

    Returns
    -------
    np.ndarray
        C/C0 values, same shape as V, bounded to [0, 1].
    """
    V = np.asarray(V, dtype=float)
    exponent = (k_th * q0 * m - k_th * C0 * V) / Q
    # clip exponent to avoid overflow in exp() for extreme parameter draws
    exponent = np.clip(exponent, -500, 500)
    ratio = 1.0 / (1.0 + np.exp(exponent))
    return np.clip(ratio, 0.0, 1.0)


def dynamic_binding_capacity(V, C0, q0, k_th, m, Q, threshold=0.10):
    """
    Compute the dynamic binding capacity (DBC) at a given breakthrough
    threshold (e.g. 10% C/C0, a common industry convention).

    Returns the load (g of target per L resin) at the throughput volume
    where C/C0 first crosses `threshold`.
    """
    curve = thomas_breakthrough(V, C0, q0, k_th, m, Q)
    idx = np.searchsorted(curve, threshold)
    if idx >= len(V):
        # never crossed threshold in the simulated volume range
        v_break = V[-1]
    else:
        v_break = V[idx]
    dbc = (C0 * v_break) / m  # g loaded per L resin at breakthrough
    return dbc, v_break


def simulate_impurity_curve(V, C0_imp, q0_imp, k_th_imp, m, Q):
    """
    Impurities typically bind more weakly than the target molecule
    (lower q0, different k_th), so they break through earlier. This
    reuses the same Thomas model with impurity-specific parameters.
    """
    return thomas_breakthrough(V, C0_imp, q0_imp, k_th_imp, m, Q)


if __name__ == "__main__":
    # quick sanity check / example curve
    V = np.linspace(0, 50, 200)
    curve = thomas_breakthrough(V, C0=5.0, q0=40.0, k_th=0.15, m=1.0, Q=0.5)
    dbc, v_break = dynamic_binding_capacity(V, C0=5.0, q0=40.0, k_th=0.15, m=1.0, Q=0.5)
    print(f"DBC (10% breakthrough): {dbc:.2f} g/L at V={v_break:.2f} L")
