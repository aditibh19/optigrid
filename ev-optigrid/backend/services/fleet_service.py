"""Fleet charging allocation (spec §16): wraps optimization.multi_ev_optimizer for the API."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from optimization.multi_ev_optimizer import (
    Allocation, ChargeRequest, ChargerCapacity, allocate_fleet_charging, validate_allocation,
)


def _first_come_first_served(requests, chargers, grid_capacity_kw) -> list[Allocation]:
    """Naive baseline: serve vehicles in the order given; same physical constraints as the optimiser."""
    remaining = {c.charger_id: c.power_kw for c in chargers}
    grid_left, out = grid_capacity_kw, []
    for r in requests:
        if r.desired_kw <= 0 or grid_left <= 1e-9:
            continue
        cid = max(remaining, key=lambda k: remaining[k], default=None)
        if cid is None or remaining[cid] <= 1e-9:
            continue
        kw = min(r.desired_kw, r.max_kw, remaining[cid], grid_left)
        if kw <= 1e-9:
            continue
        out.append(Allocation(vehicle_id=r.vehicle_id, charger_id=cid, allocated_kw=round(kw, 3)))
        remaining[cid] -= kw
        grid_left -= kw
    return out


def _service_score(requests, allocations) -> float:
    """Urgency-weighted share of requested power actually delivered, in percent."""
    got = {a.vehicle_id: a.allocated_kw for a in allocations}
    wanted = [r for r in requests if r.desired_kw > 0]
    total = sum(r.value_weight for r in wanted)
    if total <= 0:
        return 100.0
    return 100.0 * sum(r.value_weight * min(1.0, got.get(r.vehicle_id, 0.0) / r.desired_kw) for r in wanted) / total


def allocate(req) -> dict:
    requests, need_kwh = [], {}
    for v in req.vehicles:
        need = max(0.0, (v.target_soc_pct - v.current_soc_pct) / 100.0 * v.battery_capacity_kwh)
        need_kwh[v.vehicle_id] = need
        desired = min(v.max_charge_rate_kw, need / (v.deadline_hours * req.charging_efficiency)) if need > 0 else 0.0
        shortfall = max(0.0, v.target_soc_pct - v.current_soc_pct) / 100.0
        requests.append(ChargeRequest(vehicle_id=v.vehicle_id, desired_kw=desired, max_kw=v.max_charge_rate_kw,
                                      value_weight=v.urgency * (1.0 + shortfall)))
    chargers = [ChargerCapacity(charger_id=c.charger_id, power_kw=c.power_kw) for c in req.chargers]

    allocations = allocate_fleet_charging(requests, chargers, req.grid_capacity_kw)
    baseline = _first_come_first_served(requests, chargers, req.grid_capacity_kw)
    violations = validate_allocation(allocations, requests, chargers, req.grid_capacity_kw)

    by_vehicle = {a.vehicle_id: a for a in allocations}
    used = sum(a.allocated_kw for a in allocations)
    rows = []
    for v, r in zip(req.vehicles, requests):
        a = by_vehicle.get(v.vehicle_id)
        if r.desired_kw <= 0:
            status, reason = "at_target", "Already at or above its target."
        elif a is None:
            status = "waiting"
            reason = "Grid limit reached." if req.grid_capacity_kw - used <= 1e-6 else "No free charger."
        elif a.allocated_kw + 1e-6 < r.desired_kw:
            status, reason = "partial", "Limited by charger power or the grid."
        else:
            status, reason = "charging", "Full requested power."
        rows.append({"vehicle_id": v.vehicle_id, "name": v.name, "urgency": v.urgency,
                     "needs_kwh": round(need_kwh[v.vehicle_id], 2), "desired_kw": round(r.desired_kw, 2),
                     "allocated_kw": a.allocated_kw if a else 0.0, "charger_id": a.charger_id if a else None,
                     "status": status, "reason": reason,
                     "minutes_to_target": (round(need_kwh[v.vehicle_id] / (a.allocated_kw * req.charging_efficiency) * 60)
                                           if a and a.allocated_kw > 0 else None)})
    charger_rows = []
    for c in req.chargers:
        on_charger = [a for a in allocations if a.charger_id == c.charger_id]
        charger_rows.append({"charger_id": c.charger_id, "power_kw": c.power_kw,
                             "allocated_kw": round(sum(a.allocated_kw for a in on_charger), 3),
                             "vehicle_ids": [a.vehicle_id for a in on_charger]})
    return {"vehicles": rows, "chargers": charger_rows,
            "totals": {"grid_capacity_kw": req.grid_capacity_kw, "grid_used_kw": round(used, 2),
                       "grid_utilisation_pct": round(100.0 * used / req.grid_capacity_kw, 1),
                       "vehicles_charging": len(allocations), "vehicles_waiting": sum(1 for r in rows if r["status"] == "waiting")},
            "constraint_violations": violations,
            "service_score_pct": {"optimised": round(_service_score(requests, allocations), 1),
                                  "first_come_first_served": round(_service_score(requests, baseline), 1)},
            "grid_used_kw_first_come": round(sum(a.allocated_kw for a in baseline), 2),
            "note": "Each charger is modelled as a power pool that can serve several vehicles at once (like a "
                    "multi-connector unit); every vehicle uses exactly one charger. Service score = urgency-weighted "
                    "share of requested power delivered. The allocator is a greedy heuristic (value per kW), "
                    "constraint-safe but not globally optimal."}
