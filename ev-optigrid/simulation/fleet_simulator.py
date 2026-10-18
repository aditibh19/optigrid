"""
Fleet charging simulator (Phase 7, spec §15).

Simulates `num_evs` vehicles sharing `num_chargers` chargers and a shared
`grid_capacity_kw` ceiling over a fixed horizon, under one charging
algorithm at a time, and reports the metrics spec §15 asks the What-If
Simulator to compare across algorithms:

    Total Cost, Peak Load, Waiting Time, SOC Violations, Deadline
    Violations, Battery Degradation, Renewable Utilization, Charger
    Utilization, Energy Purchased

Every number reported is computed from the actual simulated trajectory —
nothing here is a hardcoded or pre-baked result (spec §42).

This module is deliberately separate from `experiment_runner.py`: this file
runs *one* (algorithm, seed) simulation; `experiment_runner.py` runs many of
those (across algorithms and/or repeated seeds) and aggregates mean/std for
the Research Dashboard (§31).
"""
from dataclasses import dataclass, field

import numpy as np

from optimization.mdp import MDPConfig, N_PRICE, N_GRID, N_SOLAR
from optimization.reward_model import resolve_weights, real_electricity_cost, DEFAULT_PRICE_VALUES
from optimization.battery_model import compute_degradation_cost
from optimization.transition_model import TransitionModel
from optimization.policy import get_or_solve_policy
from simulation.baseline_policies import (
    VehicleDecisionContext, greedy_policy, fixed_schedule_policy,
    price_threshold_policy, priority_policy, urgency_score,
)


@dataclass
class EVInstance:
    id: int
    battery_capacity_kwh: float
    max_charge_rate_kw: float
    charging_efficiency: float
    soc_pct: float
    target_soc_pct: float
    arrival_slot: int
    deadline_slot: int
    # Running totals, filled in during simulation:
    energy_delivered_kwh: float = 0.0
    cost_incurred: float = 0.0
    degradation_cost: float = 0.0
    waiting_slots: int = 0        # slots where it wanted power but got none/less than desired
    got_charger_at_least_once: bool = False


@dataclass
class FleetSimulationConfig:
    num_evs: int
    num_chargers: int
    charger_power_kw: float
    grid_capacity_kw: float
    horizon_slots: int
    slot_minutes: int = 15
    seed: int = 42

    # Fleet composition (illustrative defaults; SYNTHETIC per spec §10/§29)
    battery_capacity_kwh_range: tuple = (40.0, 80.0)
    vehicle_max_rate_kw_range: tuple = (7.0, 50.0)
    charging_efficiency: float = 0.90
    initial_soc_range: tuple = (20.0, 60.0)
    target_soc_default: float = 90.0

    @property
    def slot_hours(self) -> float:
        return self.slot_minutes / 60.0


@dataclass
class SimulationResult:
    algorithm: str
    total_cost: float
    peak_load_kw: float
    mean_waiting_slots: float
    soc_violations: int
    deadline_violations: int
    total_degradation_cost: float
    renewable_utilization_pct: float
    charger_utilization_pct: float
    energy_purchased_kwh: float


def generate_synthetic_fleet(config: FleetSimulationConfig, rng: np.random.Generator) -> list[EVInstance]:
    fleet = []
    for i in range(config.num_evs):
        battery = rng.uniform(*config.battery_capacity_kwh_range)
        max_rate = rng.uniform(*config.vehicle_max_rate_kw_range)
        soc = rng.uniform(*config.initial_soc_range)
        arrival = int(rng.integers(0, max(1, config.horizon_slots // 3)))
        # Deadline is a random point in the back half of the horizon, so
        # every vehicle has a nontrivial but bounded amount of slack.
        deadline = int(rng.integers(config.horizon_slots // 2, config.horizon_slots))
        fleet.append(EVInstance(
            id=i,
            battery_capacity_kwh=round(battery, 1),
            max_charge_rate_kw=round(min(max_rate, config.charger_power_kw), 1),
            charging_efficiency=config.charging_efficiency,
            soc_pct=round(soc, 1),
            target_soc_pct=config.target_soc_default,
            arrival_slot=arrival,
            deadline_slot=deadline,
        ))
    return fleet


def generate_exogenous_sequence(config: FleetSimulationConfig, rng: np.random.Generator):
    """
    A single shared price/grid/solar bucket sequence for the whole fleet
    (they're all plugged into the same regional grid). SIMULATED per spec
    §29 — in production this would come from `ml/*_forecaster.py` outputs
    plus live `electricity_prices`/`grid_load`/`solar_generation` rows.
    """
    tm = TransitionModel()
    price_idx, grid_idx, solar_idx = 1, 1, 0  # start at medium/medium/none
    price_seq, grid_seq, solar_seq = [], [], []
    for _ in range(config.horizon_slots):
        price_seq.append(price_idx)
        grid_seq.append(grid_idx)
        solar_seq.append(solar_idx)
        price_idx = rng.choice(N_PRICE, p=tm.price_matrix[price_idx])
        grid_idx = rng.choice(N_GRID, p=tm.grid_matrix[grid_idx])
        solar_idx = rng.choice(N_SOLAR, p=tm.solar_matrix[solar_idx])
    return price_seq, grid_seq, solar_seq


def _sdp_desired_power(ev: EVInstance, t: int, price_idx: int, grid_idx: int, solar_idx: int,
                        config: FleetSimulationConfig, weights) -> float:
    remaining = max(1, ev.deadline_slot - t)
    mdp_config = MDPConfig(
        battery_capacity_kwh=ev.battery_capacity_kwh,
        max_charge_rate_kw=ev.max_charge_rate_kw,
        charging_efficiency=ev.charging_efficiency,
        slot_minutes=config.slot_minutes,
        horizon_slots=remaining,
    )
    policy, _cached = get_or_solve_policy(
        mdp_config, weights, target_soc_pct=ev.target_soc_pct, minimum_safe_soc_pct=ev.target_soc_pct * 0.8,
    )
    return policy.action_kw(0, ev.soc_pct, price_idx, grid_idx, solar_idx)


def run_fleet_simulation(
    config: FleetSimulationConfig,
    algorithm: str,
    fixed_schedule_window: tuple = None,
    price_threshold_bucket: int = 1,
    sdp_profile: str = "balanced",
    debug_return_fleet: bool = False,
) -> SimulationResult:
    assert algorithm in ("greedy", "fixed_schedule", "price_threshold", "priority", "sdp"), \
        f"Unknown algorithm: {algorithm}"

    rng = np.random.default_rng(config.seed)
    fleet = generate_synthetic_fleet(config, rng)
    price_seq, grid_seq, solar_seq = generate_exogenous_sequence(config, rng)

    if fixed_schedule_window is None:
        # Default off-peak assumption: back third of the horizon.
        fixed_schedule_window = (2 * config.horizon_slots // 3, config.horizon_slots)

    weights = resolve_weights(sdp_profile)
    load_per_slot = np.zeros(config.horizon_slots)
    chargers_in_use_per_slot = np.zeros(config.horizon_slots)
    renewable_energy_kwh = 0.0
    total_energy_kwh = 0.0

    for t in range(config.horizon_slots):
        price_idx, grid_idx, solar_idx = price_seq[t], grid_seq[t], solar_seq[t]

        # 1. Every active (arrived, not-yet-past-deadline, below target) EV
        #    states its desired power for this slot.
        requests = []  # (ev, desired_kw, urgency)
        for ev in fleet:
            if not (ev.arrival_slot <= t <= ev.deadline_slot):
                continue
            if ev.soc_pct >= ev.target_soc_pct:
                continue

            ctx = VehicleDecisionContext(
                t=t, soc_pct=ev.soc_pct, target_soc_pct=ev.target_soc_pct,
                deadline_slot=ev.deadline_slot, price_idx=price_idx, grid_idx=grid_idx,
                solar_idx=solar_idx,
                config=MDPConfig(battery_capacity_kwh=ev.battery_capacity_kwh,
                                  max_charge_rate_kw=ev.max_charge_rate_kw,
                                  charging_efficiency=ev.charging_efficiency,
                                  slot_minutes=config.slot_minutes),
            )
            if algorithm == "greedy":
                desired = greedy_policy(ctx)
            elif algorithm == "fixed_schedule":
                desired = fixed_schedule_policy(ctx, *fixed_schedule_window)
            elif algorithm == "price_threshold":
                desired = price_threshold_policy(ctx, price_threshold_bucket)
            elif algorithm == "priority":
                desired = priority_policy(ctx)
            else:  # sdp
                desired = _sdp_desired_power(ev, t, price_idx, grid_idx, solar_idx, config, weights)

            if desired > 0:
                requests.append((ev, desired, urgency_score(ctx)))

        # 2. Arbitrate: who actually gets a charger this slot, when demand
        #    exceeds supply. This is where "greedy" and "priority" actually
        #    differ — their desired-power functions are otherwise the same
        #    (both want max rate whenever below target). Greedy/fixed-
        #    schedule/price-threshold allocate first-come-first-served
        #    (by vehicle registration order, standing in for arrival
        #    order); "priority" and "sdp" allocate to the most urgent
        #    vehicle first. Allocating everything by urgency regardless of
        #    algorithm — an earlier version of this function did that —
        #    would make greedy and priority produce identical results,
        #    silently erasing the one thing "priority" is supposed to
        #    demonstrate.
        if algorithm in ("priority", "sdp"):
            requests.sort(key=lambda r: r[2], reverse=True)   # most urgent first
        else:
            requests.sort(key=lambda r: r[0].id)               # FCFS by registration order
        allocated_this_slot = []
        chargers_used = 0
        grid_remaining = config.grid_capacity_kw

        for ev, desired, _urgency in requests:
            if chargers_used >= config.num_chargers:
                ev.waiting_slots += 1
                continue
            power = min(desired, config.charger_power_kw, ev.max_charge_rate_kw, grid_remaining)
            if power <= 0:
                ev.waiting_slots += 1
                continue
            allocated_this_slot.append((ev, power))
            chargers_used += 1
            grid_remaining -= power

        # 3. Apply the allocated power: update SOC, cost, degradation, load.
        slot_total_load = 0.0
        for ev, power_kw in allocated_this_slot:
            soc_before = ev.soc_pct
            energy_kwh = power_kw * config.slot_hours * ev.charging_efficiency
            soc_gain = (energy_kwh / ev.battery_capacity_kwh) * 100.0
            ev.soc_pct = min(100.0, ev.soc_pct + soc_gain)

            ev.energy_delivered_kwh += energy_kwh
            ev.cost_incurred += real_electricity_cost(power_kw, price_idx, config.slot_hours)
            ev.degradation_cost += compute_degradation_cost(
                soc_before=soc_before, soc_after=ev.soc_pct,
                charge_power_kw=power_kw, max_charge_rate_kw=ev.max_charge_rate_kw,
            )
            ev.got_charger_at_least_once = True

            slot_total_load += power_kw
            total_energy_kwh += energy_kwh
            if solar_idx == N_SOLAR - 1:  # "high" solar bucket
                renewable_energy_kwh += energy_kwh

        load_per_slot[t] = slot_total_load
        chargers_used_frac = len(allocated_this_slot) / max(1, config.num_chargers)
        chargers_in_use_per_slot[t] = chargers_used_frac

    # ── Metrics ──────────────────────────────────────────────────────────
    total_cost = sum(ev.cost_incurred for ev in fleet)
    peak_load_kw = float(load_per_slot.max()) if config.horizon_slots > 0 else 0.0
    mean_waiting = float(np.mean([ev.waiting_slots for ev in fleet])) if fleet else 0.0
    soc_violations = sum(1 for ev in fleet if ev.soc_pct < ev.target_soc_pct * 0.8)  # below "minimum safe"
    deadline_violations = sum(1 for ev in fleet if ev.soc_pct < ev.target_soc_pct)
    total_degradation = sum(ev.degradation_cost for ev in fleet)
    renewable_pct = (renewable_energy_kwh / total_energy_kwh * 100.0) if total_energy_kwh > 0 else 0.0
    charger_utilization_pct = float(chargers_in_use_per_slot.mean()) * 100.0

    if debug_return_fleet:
        for ev in fleet:
            print(f"  [debug] ev={ev.id} final_soc={ev.soc_pct:.1f} target={ev.target_soc_pct} "
                  f"arrival={ev.arrival_slot} deadline={ev.deadline_slot} waiting={ev.waiting_slots}")

    return SimulationResult(
        algorithm=algorithm,
        total_cost=round(total_cost, 2),
        peak_load_kw=round(peak_load_kw, 2),
        mean_waiting_slots=round(mean_waiting, 2),
        soc_violations=soc_violations,
        deadline_violations=deadline_violations,
        total_degradation_cost=round(total_degradation, 4),
        renewable_utilization_pct=round(renewable_pct, 2),
        charger_utilization_pct=round(charger_utilization_pct, 2),
        energy_purchased_kwh=round(total_energy_kwh, 2),
    )
