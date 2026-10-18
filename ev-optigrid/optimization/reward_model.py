"""
Multi-objective cost function (spec §7) and battery degradation integration.

    J = w1*electricity_cost + w2*battery_degradation_cost + w3*grid_peak_penalty
      + w4*waiting_cost + w5*travel_cost + w6*unmet_energy_penalty
      + w7*deadline_violation_penalty - w8*renewable_energy_reward

This module supplies the *per-slot* cost C(s,a) consumed by
`value_iteration.py`'s Bellman recursion, plus a *terminal* cost applied at
the deadline slot for unmet-energy / deadline-violation penalties (§6/§13).

Bucket → representative numeric value mappings (price/grid/solar) are
illustrative defaults for when the caller doesn't supply live/predicted
values; in the real pipeline these come from `ml/price_forecaster.py`,
`ml/grid_forecaster.py`, `ml/solar_forecaster.py` (see
optimization_service.py, Phase 12) and are passed in explicitly.
"""
from dataclasses import dataclass

from optimization.battery_model import compute_degradation_cost, BatteryDegradationWeights
from optimization.mdp import soc_from_bucket_index, DEFAULT_ACTIONS_KW


# ── Default representative values for each discrete bucket (illustrative) ──
DEFAULT_PRICE_VALUES = {0: 4.5, 1: 8.0, 2: 13.5}      # ₹/kWh: low, medium, high
DEFAULT_GRID_LOAD_VALUES = {0: 35.0, 1: 65.0, 2: 90.0}  # % of grid capacity
DEFAULT_SOLAR_AVAIL_VALUES = {0: 0.0, 1: 0.4, 2: 1.0}   # fraction of max deliverable power

# Worst-case per-slot electricity spend (max action, at the highest price
# bucket) used to normalize electricity_cost into roughly the same [0,1]-ish
# range as the other cost terms. Without this, a real-currency cost term
# (tens to hundreds) completely swamps the unmet/deadline penalty terms
# (which are deliberately expressed as normalized SOC fractions), and the
# profile weights stop having any visible effect — this constant is what
# makes `w_cost`, `w_unmet`, etc. actually comparable in the Bellman cost.
_WORST_CASE_PRICE = max(DEFAULT_PRICE_VALUES.values())

# Global reference power for normalizing electricity_cost, grid_penalty, and
# renewable_reward — deliberately NOT the calling vehicle's own
# max_charge_rate_kw. Using a per-vehicle denominator would make drawing,
# say, 5 kW look exactly as "expensive"/"grid-stressing" for a car whose
# charger tops out at 7 kW as it does for a car on a 50 kW charger, purely
# because 5/7 and 5/50 are different *fractions* — even though 5 kW is the
# same, genuinely small, real-world load on the grid either way. That
# miscalibration was caught via a scenario where a slow (7 kW) charger with
# a tight deadline was recommended 0 kW for its entire session despite
# having nothing to lose by charging — see docs/MDP.md §12. Battery
# degradation is the one exception that legitimately stays vehicle-relative
# (see `compute_degradation_cost`'s use of the vehicle's own
# max_charge_rate_kw): stressing a car's own charging limit is what
# matters for wear, regardless of how that limit compares to other cars.
GLOBAL_REFERENCE_MAX_KW = max(DEFAULT_ACTIONS_KW)


@dataclass
class ProfileWeights:
    w_cost: float
    w_battery: float
    w_grid: float
    w_wait: float
    w_travel: float
    w_unmet: float
    w_deadline: float
    w_renewable: float


# Six user profiles (spec §7). Weights are relative, not required to sum to 1 —
# what matters is the ratio between terms, which is what actually changes
# behaviour when the profile is switched (verified in the demo script).
PROFILE_WEIGHTS: dict[str, ProfileWeights] = {
    "save_money":     ProfileWeights(w_cost=3.0, w_battery=0.5, w_grid=0.3, w_wait=0.3, w_travel=0.3, w_unmet=5.0, w_deadline=4.0, w_renewable=0.3),
    "fastest":        ProfileWeights(w_cost=0.3, w_battery=0.2, w_grid=0.1, w_wait=3.0, w_travel=2.0, w_unmet=5.0, w_deadline=6.0, w_renewable=0.1),
    "battery_health": ProfileWeights(w_cost=0.5, w_battery=3.0, w_grid=0.3, w_wait=0.5, w_travel=0.3, w_unmet=5.0, w_deadline=4.0, w_renewable=0.3),
    "green":          ProfileWeights(w_cost=0.5, w_battery=0.5, w_grid=0.5, w_wait=0.5, w_travel=0.3, w_unmet=5.0, w_deadline=4.0, w_renewable=3.0),
    "balanced":       ProfileWeights(w_cost=1.0, w_battery=1.0, w_grid=1.0, w_wait=1.0, w_travel=1.0, w_unmet=5.0, w_deadline=4.0, w_renewable=1.0),
    "custom":         ProfileWeights(w_cost=1.0, w_battery=1.0, w_grid=1.0, w_wait=1.0, w_travel=1.0, w_unmet=5.0, w_deadline=4.0, w_renewable=1.0),
}


def step_cost_note():
    """
    Design note (see docs/MDP.md and docs/CHARGER_SCORING.md):

    `w_wait` and `w_travel` deliberately do NOT appear inside `step_cost`
    below. This per-slot SDP decides "how much to charge, and when", given
    a station already selected — queueing/travel time are properties of
    *which station* you go to, not of the charging-rate decision at a fixed
    station. Those two weights are consumed by the Charging Opportunity
    Score (`optimization/station_optimizer.py`) when ranking candidate
    stations, and by `multi_ev_optimizer.py` when a fleet-level choice has
    to trade queueing against everything else. Splitting it this way keeps
    the SDP's state space small (no need to model "which station" as part
    of the MDP state) while still respecting all eight weights somewhere in
    the pipeline.
    """


def step_cost(
    soc_before_pct: float,
    soc_after_pct: float,
    action_kw: float,
    max_charge_rate_kw: float,
    price_idx: int,
    grid_idx: int,
    solar_idx: int,
    slot_hours: float,
    weights: ProfileWeights,
    price_values: dict = DEFAULT_PRICE_VALUES,
    grid_values: dict = DEFAULT_GRID_LOAD_VALUES,
    solar_values: dict = DEFAULT_SOLAR_AVAIL_VALUES,
) -> float:
    """C(s, a) for a single time slot."""
    price_per_kwh = price_values[price_idx]
    grid_load_frac = grid_values[grid_idx] / 100.0
    solar_avail_frac = solar_values[solar_idx]

    energy_kwh = action_kw * slot_hours
    raw_electricity_cost = energy_kwh * price_per_kwh
    # Normalized against a GLOBAL reference power (see GLOBAL_REFERENCE_MAX_KW
    # above), not this vehicle's own max rate — 1.0 would mean "charging at
    # the global reference power, at the worst-case price, this whole slot".
    worst_case_cost = GLOBAL_REFERENCE_MAX_KW * slot_hours * _WORST_CASE_PRICE
    electricity_cost = raw_electricity_cost / worst_case_cost

    degradation_cost = compute_degradation_cost(
        soc_before=soc_before_pct,
        soc_after=soc_after_pct,
        charge_power_kw=action_kw,
        max_charge_rate_kw=max_charge_rate_kw,   # vehicle-relative — see note above
    )

    # Grid peak penalty: charging harder while grid load is already high is
    # penalized super-linearly to discourage piling onto a stressed grid.
    # Normalized against the GLOBAL reference power, so a small charger's
    # genuinely small grid draw reads as small.
    grid_penalty = (grid_load_frac ** 2) * (action_kw / GLOBAL_REFERENCE_MAX_KW)

    # Renewable reward: charging while solar is abundant is rewarded
    # proportional to how much of the action's energy could plausibly be
    # solar-sourced. Same global normalization.
    renewable_reward = solar_avail_frac * (action_kw / GLOBAL_REFERENCE_MAX_KW)

    return (
        weights.w_cost * electricity_cost
        + weights.w_battery * degradation_cost
        + weights.w_grid * grid_penalty
        - weights.w_renewable * renewable_reward
    )


def terminal_cost(
    final_soc_pct: float,
    target_soc_pct: float,
    minimum_safe_soc_pct: float,
    weights: ProfileWeights,
) -> float:
    """
    Applied only at the last slot before the deadline. Penalizes falling
    short of the target, and applies an extra, larger penalty for falling
    below the minimum-safe SOC needed to actually complete the journey.
    """
    unmet = max(0.0, target_soc_pct - final_soc_pct)
    unmet_penalty = weights.w_unmet * (unmet / 100.0)

    deadline_violation = max(0.0, minimum_safe_soc_pct - final_soc_pct)
    deadline_penalty = weights.w_deadline * (deadline_violation / 100.0) * 5.0  # extra severity

    return unmet_penalty + deadline_penalty


def real_electricity_cost(action_kw: float, price_idx: int, slot_hours: float,
                           price_values: dict = DEFAULT_PRICE_VALUES) -> float:
    """
    Actual currency cost (₹) of one slot's charging — used for
    user-facing numbers (dashboard "Estimated Cost", comparison screen),
    as opposed to the normalized `electricity_cost` term consumed inside
    the Bellman cost function above.
    """
    return action_kw * slot_hours * price_values[price_idx]


def resolve_weights(profile: str, custom_overrides: dict | None = None) -> ProfileWeights:
    base = PROFILE_WEIGHTS.get(profile, PROFILE_WEIGHTS["balanced"])
    if profile != "custom" or not custom_overrides:
        return base
    merged = {**base.__dict__, **{k: v for k, v in custom_overrides.items() if v is not None}}
    return ProfileWeights(**merged)
