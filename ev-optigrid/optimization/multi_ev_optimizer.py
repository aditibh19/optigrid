"""
Multi-EV / fleet joint optimizer (Phase 17, spec §16).

Distinct from the simple "priority" baseline in
`simulation/baseline_policies.py` (which sorts by urgency and allocates
whole chargers first-come/most-urgent-first): this allocator can split a
charger's power fractionally across the allocation decision and ranks by
VALUE DENSITY (urgency-weighted benefit per kW) rather than urgency alone,
so a vehicle that's moderately urgent but can make excellent use of a
little power isn't starved by one extremely urgent vehicle hogging an
entire charger it can't even fully use (e.g. a slow AC-only vehicle
sharing a fast DC charger's rated power with a car that could use all of
it).

Hard constraints enforced BY CONSTRUCTION, not by hoping the ranking works
out (spec §16: "prevent charger conflicts, grid capacity violations,
impossible charging schedules"):
  - total power to any one vehicle never exceeds its own max charge rate
  - total power across all vehicles on one charger never exceeds that
    charger's rated power
  - total power across the whole fleet never exceeds grid_capacity_kw
"""
from dataclasses import dataclass


@dataclass
class ChargeRequest:
    vehicle_id: int
    desired_kw: float          # how much this vehicle wants (from its own policy/urgency)
    max_kw: float               # this vehicle's own ceiling (min of vehicle and assigned-charger rate)
    value_weight: float         # urgency or COS-derived "how much this allocation matters", > 0


@dataclass
class ChargerCapacity:
    charger_id: int
    power_kw: float             # this charger's rated max output


@dataclass
class Allocation:
    vehicle_id: int
    charger_id: int
    allocated_kw: float


def allocate_fleet_charging(requests, chargers, grid_capacity_kw):
    """
    Assigns each requesting vehicle to at most one charger (one vehicle,
    one plug — matches how physical charging works) and a power level,
    maximizing total value_weight-weighted throughput subject to the three
    hard constraints listed above. Greedy by value density (value_weight
    per kW) — not globally optimal in the general case (that would be a
    proper LP/assignment solve), but constraint-safe by construction and
    fast enough to run every simulation slot, which matters more here than
    provable optimality.
    """
    if not requests or not chargers:
        return []

    ranked_requests = sorted(
        requests,
        key=lambda r: (r.value_weight / max(r.desired_kw, 1e-6), r.value_weight),
        reverse=True,
    )

    charger_remaining = {c.charger_id: c.power_kw for c in chargers}
    grid_remaining = grid_capacity_kw
    assigned_vehicles = set()
    allocations = []

    for req in ranked_requests:
        if req.vehicle_id in assigned_vehicles or req.desired_kw <= 0 or grid_remaining <= 0:
            continue

        best_charger_id = max(charger_remaining, key=lambda cid: charger_remaining[cid], default=None)
        if best_charger_id is None or charger_remaining[best_charger_id] <= 0:
            continue

        allocated_kw = min(req.desired_kw, req.max_kw, charger_remaining[best_charger_id], grid_remaining)
        if allocated_kw <= 1e-9:
            continue

        allocations.append(Allocation(vehicle_id=req.vehicle_id, charger_id=best_charger_id,
                                       allocated_kw=round(allocated_kw, 3)))
        charger_remaining[best_charger_id] -= allocated_kw
        grid_remaining -= allocated_kw
        assigned_vehicles.add(req.vehicle_id)

    return allocations


def validate_allocation(allocations, requests, chargers, grid_capacity_kw):
    """
    Returns a list of constraint-violation descriptions (empty if none) —
    used by tests and by `simulation/experiment_runner.py` to confirm the
    allocator never produces a physically impossible schedule, which spec
    §16 calls out explicitly.
    """
    violations = []
    max_kw_by_vehicle = {r.vehicle_id: r.max_kw for r in requests}
    charger_power = {c.charger_id: c.power_kw for c in chargers}

    per_vehicle_total = {}
    per_charger_total = {}
    for a in allocations:
        per_vehicle_total[a.vehicle_id] = per_vehicle_total.get(a.vehicle_id, 0.0) + a.allocated_kw
        per_charger_total[a.charger_id] = per_charger_total.get(a.charger_id, 0.0) + a.allocated_kw

    for vehicle_id, total in per_vehicle_total.items():
        if total > max_kw_by_vehicle.get(vehicle_id, float("inf")) + 1e-6:
            violations.append(f"vehicle {vehicle_id} allocated {total}kW exceeds its max {max_kw_by_vehicle[vehicle_id]}kW")

    for charger_id, total in per_charger_total.items():
        if total > charger_power.get(charger_id, float("inf")) + 1e-6:
            violations.append(f"charger {charger_id} allocated {total}kW exceeds its rated {charger_power[charger_id]}kW")

    total_grid = sum(a.allocated_kw for a in allocations)
    if total_grid > grid_capacity_kw + 1e-6:
        violations.append(f"total allocation {total_grid}kW exceeds grid capacity {grid_capacity_kw}kW")

    return violations
