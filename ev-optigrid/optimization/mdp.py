"""
MDP state/action space definition (Phase 4, spec §6).

FORMULATION CHOICE (documented in full in docs/MDP.md — read that before the
viva): this is modeled as a **finite-horizon** stochastic dynamic program,
solved by backward induction from the user's departure deadline back to now.
This is deliberately NOT infinite-horizon discounted value iteration,
because a charging decision problem with a known deadline is naturally
finite-horizon — time-to-deadline does not need to be a state dimension
(it's the backward-induction index itself), which keeps the state space
small enough to solve exactly at request time.

State (per time slot t):
    s = (soc_bucket, price_bucket, grid_bucket, solar_bucket)

Action (per time slot):
    a = charging power in kW, drawn from a configurable discrete set,
    implicitly capped by the vehicle's and charger's max rate at solve time.
"""
from dataclasses import dataclass, field
import numpy as np


# ── Discretization ──────────────────────────────────────────────────────
SOC_STEP = 5.0
SOC_BUCKETS = np.arange(0.0, 100.0 + SOC_STEP, SOC_STEP)          # 0,5,...,100  (21 buckets)
N_SOC = len(SOC_BUCKETS)

PRICE_LEVELS = ("low", "medium", "high")
GRID_LEVELS = ("low", "medium", "high")
SOLAR_LEVELS = ("none", "some", "high")

N_PRICE = len(PRICE_LEVELS)
N_GRID = len(GRID_LEVELS)
N_SOLAR = len(SOLAR_LEVELS)

DEFAULT_ACTIONS_KW = (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0)


def nearest_soc_bucket_index(soc_pct: float) -> int:
    idx = int(round(soc_pct / SOC_STEP))
    return max(0, min(N_SOC - 1, idx))


def soc_from_bucket_index(idx: int) -> float:
    return float(SOC_BUCKETS[idx])


def soc_transition_distribution(soc_before_pct: float, gain_pct: float) -> list[tuple[float, int]]:
    """
    Returns [(probability, soc_bucket_index), ...] for the continuous SOC
    outcome `soc_before_pct + gain_pct` (clamped to [0,100]), using linear
    interpolation between the two bracketing buckets rather than snapping
    to the single nearest one.

    Why this matters: with deterministic nearest-bucket rounding, a small
    per-slot gain (e.g. a 5 kW charger on a large battery, gain < half a
    bucket width) rounds back to the SAME bucket every single slot,
    forever — the Markov chain has a self-loop for that (state, action)
    pair, so backward induction sees "charging this way never helps",
    even though the real continuous SOC obviously does advance and
    eventually crosses a bucket boundary. This was caught by a fleet
    simulation where a slow (8.2 kW) charger's vehicle received literally
    zero charge for its entire session because its per-slot gain (~1.8pp)
    was smaller than half the 5pp bucket width (see docs/MDP.md §12).

    Linear interpolation fixes this by making the EXPECTED next bucket
    match the true continuous value on every single transition, so
    repeated small gains correctly accumulate probability mass toward the
    next bucket over successive slots instead of being discarded outright.
    """
    soc_after = max(0.0, min(100.0, soc_before_pct + gain_pct))
    exact_idx = soc_after / SOC_STEP
    idx_low = int(np.floor(exact_idx))
    idx_high = int(np.ceil(exact_idx))
    idx_low = max(0, min(N_SOC - 1, idx_low))
    idx_high = max(0, min(N_SOC - 1, idx_high))

    if idx_low == idx_high:
        return [(1.0, idx_low)]

    frac_high = exact_idx - idx_low   # weight toward the upper bucket
    frac_low = 1.0 - frac_high
    return [(frac_low, idx_low), (frac_high, idx_high)]


@dataclass
class MDPConfig:
    """Everything needed to instantiate a solvable MDP for one journey/session."""
    battery_capacity_kwh: float
    max_charge_rate_kw: float          # min(vehicle max, charger max) — resolved by the caller
    charging_efficiency: float = 0.90
    slot_minutes: int = 15
    horizon_slots: int = 24            # e.g. 24 * 15min = 6 hours to deadline
    actions_kw: tuple = field(default_factory=lambda: DEFAULT_ACTIONS_KW)

    @property
    def slot_hours(self) -> float:
        return self.slot_minutes / 60.0

    def feasible_actions_kw(self) -> tuple:
        """Actions capped at the resolved max charge rate for this session."""
        return tuple(a for a in self.actions_kw if a <= self.max_charge_rate_kw + 1e-9) or (0.0,)

    def soc_gain_pct(self, action_kw: float) -> float:
        energy_kwh = action_kw * self.slot_hours * self.charging_efficiency
        return (energy_kwh / self.battery_capacity_kwh) * 100.0


def bucketize(value: float, low_high_thresholds: tuple) -> int:
    """
    Generic 3-level bucketizer: index 0 (low) if value <= t_low,
    index 2 (high) if value >= t_high, else index 1 (medium).
    """
    t_low, t_high = low_high_thresholds
    if value <= t_low:
        return 0
    if value >= t_high:
        return 2
    return 1


# Illustrative default thresholds — in the real pipeline these are derived
# from the region's recent price/grid/solar distribution (see
# services/prediction_service.py, Phase 12), not hardcoded globally.
DEFAULT_PRICE_THRESHOLDS = (6.0, 11.0)          # ₹/kWh
DEFAULT_GRID_LOAD_THRESHOLDS = (50.0, 80.0)     # % of capacity
DEFAULT_SOLAR_THRESHOLDS = (0.05, 0.6)          # fraction of max deliverable power


def bucketize_price(price_per_kwh: float, thresholds: tuple = DEFAULT_PRICE_THRESHOLDS) -> int:
    return bucketize(price_per_kwh, thresholds)


def bucketize_grid_load(load_pct: float, thresholds: tuple = DEFAULT_GRID_LOAD_THRESHOLDS) -> int:
    return bucketize(load_pct, thresholds)


def bucketize_solar(avail_fraction: float, thresholds: tuple = DEFAULT_SOLAR_THRESHOLDS) -> int:
    return bucketize(avail_fraction, thresholds)
