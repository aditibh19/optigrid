"""
Transition model (Phase 4, spec §6).

Price, grid load, and solar generation each transition as a first-order
Markov chain over their discrete buckets (`optimization/mdp.py`). Two ways
to obtain a transition matrix are provided:

1. `build_default_transition_matrix` — a persistence-parameterized synthetic
   matrix (SIMULATED), used when no historical time series is available yet.
2. `estimate_transition_matrix` — maximum-likelihood estimation (with
   Laplace smoothing) from an observed bucket sequence, e.g. bucketized
   `electricity_prices` / `grid_load` / `solar_generation` history. This is
   what a production deployment would use once enough real data has
   accumulated (see ml/ for the richer point-forecast models, which the
   optimizer also consults — this Markov layer specifically captures the
   *uncertainty* the SDP needs, not just a point prediction).

SOC transition given a charging action is deterministic (battery physics,
`optimization/mdp.py::MDPConfig.soc_gain_pct`) — the uncertainty in this
problem lives in the exogenous variables (price/grid/solar), not in how much
energy a charger delivers.
"""
import numpy as np

from optimization.mdp import N_PRICE, N_GRID, N_SOLAR


def build_default_transition_matrix(n_levels: int, persistence: float = 0.7) -> np.ndarray:
    """
    A simple, documented-as-synthetic transition matrix: probability
    `persistence` of staying in the same bucket next slot, remaining
    probability split over neighboring buckets (mean-reverting rather than
    jumping from 'low' straight to 'high').
    """
    m = np.zeros((n_levels, n_levels))
    for i in range(n_levels):
        m[i, i] = persistence
        remaining = 1.0 - persistence
        neighbors = [j for j in (i - 1, i + 1) if 0 <= j < n_levels]
        if neighbors:
            for j in neighbors:
                m[i, j] = remaining / len(neighbors)
        else:
            m[i, i] = 1.0
    return m


def estimate_transition_matrix(bucket_sequence: list[int], n_levels: int, smoothing: float = 1.0) -> np.ndarray:
    """
    MLE transition matrix from an observed sequence of bucket indices, with
    additive (Laplace) smoothing so unseen transitions aren't assigned zero
    probability outright.
    """
    counts = np.full((n_levels, n_levels), smoothing)
    for a, b in zip(bucket_sequence[:-1], bucket_sequence[1:]):
        counts[a, b] += 1.0
    return counts / counts.sum(axis=1, keepdims=True)


class TransitionModel:
    def __init__(
        self,
        price_matrix: np.ndarray | None = None,
        grid_matrix: np.ndarray | None = None,
        solar_matrix: np.ndarray | None = None,
    ):
        self.price_matrix = price_matrix if price_matrix is not None else build_default_transition_matrix(N_PRICE)
        self.grid_matrix = grid_matrix if grid_matrix is not None else build_default_transition_matrix(N_GRID)
        self.solar_matrix = solar_matrix if solar_matrix is not None else build_default_transition_matrix(N_SOLAR, persistence=0.6)

        for name, m, n in (("price", self.price_matrix, N_PRICE),
                            ("grid", self.grid_matrix, N_GRID),
                            ("solar", self.solar_matrix, N_SOLAR)):
            assert m.shape == (n, n), f"{name} transition matrix must be {n}x{n}"
            assert np.allclose(m.sum(axis=1), 1.0, atol=1e-6), f"{name} transition matrix rows must sum to 1"

    def next_state_distribution(self, price_idx: int, grid_idx: int, solar_idx: int):
        """
        Returns the joint distribution over (price', grid', solar') as a
        list of (prob, price', grid', solar') tuples, assuming the three
        exogenous processes evolve independently given the current bucket
        (a standard simplifying independence assumption, documented here —
        not claimed to be exact).
        """
        out = []
        p_row = self.price_matrix[price_idx]
        g_row = self.grid_matrix[grid_idx]
        s_row = self.solar_matrix[solar_idx]
        for pi, pp in enumerate(p_row):
            if pp <= 0:
                continue
            for gi, gp in enumerate(g_row):
                if gp <= 0:
                    continue
                for si, sp in enumerate(s_row):
                    if sp <= 0:
                        continue
                    out.append((pp * gp * sp, pi, gi, si))
        return out
