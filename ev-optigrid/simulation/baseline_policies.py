"""
Baseline charging-decision policies (Phase 6, spec §15/§31).

Each baseline answers one question per vehicle per time slot: "how much
power would this vehicle *like* to draw right now, ignoring whether a
charger/grid capacity is actually available?" `fleet_simulator.py` is what
then arbitrates between competing desires under real charger/grid
constraints — these functions are deliberately capacity-agnostic so the
same desire function can be tested in isolation.

These exist specifically so the SDP's advantage is a *measured* comparison
(Research Dashboard, §31), not an assertion.
"""
from dataclasses import dataclass

from optimization.mdp import MDPConfig


@dataclass
class VehicleDecisionContext:
    """Everything a baseline policy needs to decide this slot's desired power."""
    t: int                       # current time slot index
    soc_pct: float
    target_soc_pct: float
    deadline_slot: int           # slot index by which soc must reach target
    price_idx: int
    grid_idx: int
    solar_idx: int
    config: MDPConfig


def greedy_policy(ctx: VehicleDecisionContext) -> float:
    """Always charge at max available rate until the target is reached."""
    if ctx.soc_pct >= ctx.target_soc_pct:
        return 0.0
    return ctx.config.max_charge_rate_kw


def fixed_schedule_policy(ctx: VehicleDecisionContext, window_start_slot: int, window_end_slot: int) -> float:
    """
    Charge at max rate, but only inside a fixed pre-set window (e.g. an
    assumed off-peak period), regardless of the actual live price/grid
    signal. This is the "doesn't adapt to conditions" baseline.
    """
    if ctx.soc_pct >= ctx.target_soc_pct:
        return 0.0
    if window_start_slot <= ctx.t < window_end_slot:
        return ctx.config.max_charge_rate_kw
    return 0.0


def price_threshold_policy(ctx: VehicleDecisionContext, max_price_bucket: int = 1) -> float:
    """
    Charge at max rate whenever price is at or below `max_price_bucket`
    (default: low or medium), regardless of the deadline. This is the
    "reacts to price but ignores the deadline" baseline — it can miss the
    target entirely if price never drops in time.
    """
    if ctx.soc_pct >= ctx.target_soc_pct:
        return 0.0
    if ctx.price_idx <= max_price_bucket:
        return ctx.config.max_charge_rate_kw
    # Emergency override: if we're at/past the deadline and still short,
    # charge anyway rather than silently failing the trip — mirrors the
    # feasibility floor the SDP's terminal cost provides implicitly.
    if ctx.t >= ctx.deadline_slot - 1:
        return ctx.config.max_charge_rate_kw
    return 0.0


def urgency_score(ctx: VehicleDecisionContext) -> float:
    """
    Higher = more urgent = should win contested charger/grid capacity.
    Used both by `priority_policy` (single-vehicle desire is "however much
    it takes") and by the fleet allocator when *any* algorithm has more
    simultaneous demand than capacity allows.
    """
    remaining_slots = max(1, ctx.deadline_slot - ctx.t)
    soc_gap_pct = max(0.0, ctx.target_soc_pct - ctx.soc_pct)
    return soc_gap_pct / remaining_slots


def priority_policy(ctx: VehicleDecisionContext) -> float:
    """
    Wants max rate whenever short of target — the actual prioritization
    (who *gets* a charger when several vehicles all want one) happens in
    the fleet allocator via `urgency_score`, not here. This baseline is
    the "always ask for everything, let priority sort it out" desire
    function, contrasted against FCFS allocation used for the other
    baselines.
    """
    if ctx.soc_pct >= ctx.target_soc_pct:
        return 0.0
    return ctx.config.max_charge_rate_kw


BASELINE_NAMES = ("greedy", "fixed_schedule", "price_threshold", "priority")
