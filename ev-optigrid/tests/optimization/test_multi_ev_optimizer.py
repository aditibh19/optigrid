import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from optimization.multi_ev_optimizer import (
    ChargeRequest, ChargerCapacity, allocate_fleet_charging, validate_allocation,
)


def test_empty_requests_returns_empty():
    assert allocate_fleet_charging([], [ChargerCapacity(1, 50)], 100) == []


def test_empty_chargers_returns_empty():
    assert allocate_fleet_charging([ChargeRequest(1, 10, 10, 1.0)], [], 100) == []


def test_single_request_single_charger_gets_full_desired():
    requests = [ChargeRequest(vehicle_id=1, desired_kw=20, max_kw=20, value_weight=1.0)]
    chargers = [ChargerCapacity(charger_id=1, power_kw=50)]
    allocations = allocate_fleet_charging(requests, chargers, grid_capacity_kw=100)
    assert len(allocations) == 1
    assert allocations[0].allocated_kw == 20


def test_allocation_never_exceeds_vehicle_max():
    requests = [ChargeRequest(vehicle_id=1, desired_kw=100, max_kw=7, value_weight=1.0)]
    chargers = [ChargerCapacity(charger_id=1, power_kw=50)]
    allocations = allocate_fleet_charging(requests, chargers, grid_capacity_kw=100)
    assert allocations[0].allocated_kw <= 7


def test_no_constraint_violations_under_various_scenarios():
    scenarios = [
        ([ChargeRequest(1, 50, 50, 2.0), ChargeRequest(2, 7, 7, 1.5), ChargeRequest(3, 30, 30, 5.0)],
         [ChargerCapacity(1, 50), ChargerCapacity(2, 20)], 100),
        ([ChargeRequest(i, 40, 40, float(i)) for i in range(1, 11)],
         [ChargerCapacity(1, 50), ChargerCapacity(2, 50)], 60),   # heavy contention
        ([ChargeRequest(1, 10, 10, 1.0)], [ChargerCapacity(1, 50)], 5),  # grid tighter than charger
    ]
    for requests, chargers, grid_cap in scenarios:
        allocations = allocate_fleet_charging(requests, chargers, grid_cap)
        violations = validate_allocation(allocations, requests, chargers, grid_cap)
        assert violations == [], f"violations found: {violations}"


def test_grid_capacity_limits_total_allocation():
    requests = [ChargeRequest(i, 40, 40, 1.0) for i in range(1, 6)]
    chargers = [ChargerCapacity(1, 100), ChargerCapacity(2, 100)]
    allocations = allocate_fleet_charging(requests, chargers, grid_capacity_kw=60)
    total = sum(a.allocated_kw for a in allocations)
    assert total <= 60 + 1e-6


def test_charger_power_limits_combined_allocation_on_one_charger():
    requests = [ChargeRequest(1, 40, 40, 2.0), ChargeRequest(2, 40, 40, 1.0)]
    chargers = [ChargerCapacity(charger_id=1, power_kw=50)]  # only one charger, shared
    allocations = allocate_fleet_charging(requests, chargers, grid_capacity_kw=200)
    total_on_charger_1 = sum(a.allocated_kw for a in allocations if a.charger_id == 1)
    assert total_on_charger_1 <= 50 + 1e-6


def test_each_vehicle_assigned_at_most_one_charger():
    requests = [ChargeRequest(1, 10, 10, 3.0)]
    chargers = [ChargerCapacity(1, 50), ChargerCapacity(2, 50)]
    allocations = allocate_fleet_charging(requests, chargers, grid_capacity_kw=200)
    vehicle_ids = [a.vehicle_id for a in allocations]
    assert len(vehicle_ids) == len(set(vehicle_ids))


def test_higher_value_density_request_served_before_lower():
    # vehicle A: low value, high desired power -> low density
    # vehicle B: high value, low desired power -> high density
    low_density = ChargeRequest(vehicle_id="A", desired_kw=50, max_kw=50, value_weight=1.0)
    high_density = ChargeRequest(vehicle_id="B", desired_kw=5, max_kw=5, value_weight=3.0)
    chargers = [ChargerCapacity(charger_id=1, power_kw=10)]  # not enough for both fully
    allocations = allocate_fleet_charging([low_density, high_density], chargers, grid_capacity_kw=10)
    # B (high density) should get served in full; A gets whatever's left
    b_alloc = next(a for a in allocations if a.vehicle_id == "B")
    assert b_alloc.allocated_kw == 5


def test_validate_allocation_detects_vehicle_overallocation():
    requests = [ChargeRequest(1, 10, 10, 1.0)]
    chargers = [ChargerCapacity(1, 50)]
    from optimization.multi_ev_optimizer import Allocation
    bad_allocations = [Allocation(vehicle_id=1, charger_id=1, allocated_kw=20.0)]  # exceeds max_kw=10
    violations = validate_allocation(bad_allocations, requests, chargers, 50)
    assert len(violations) > 0
    assert "vehicle 1" in violations[0]


def test_validate_allocation_detects_grid_overallocation():
    requests = [ChargeRequest(1, 100, 100, 1.0)]
    chargers = [ChargerCapacity(1, 100)]
    from optimization.multi_ev_optimizer import Allocation
    bad_allocations = [Allocation(vehicle_id=1, charger_id=1, allocated_kw=90.0)]
    violations = validate_allocation(bad_allocations, requests, chargers, grid_capacity_kw=50)
    assert any("grid capacity" in v for v in violations)


def test_validate_allocation_clean_case_has_no_violations():
    requests = [ChargeRequest(1, 10, 10, 1.0)]
    chargers = [ChargerCapacity(1, 50)]
    allocations = allocate_fleet_charging(requests, chargers, grid_capacity_kw=50)
    assert validate_allocation(allocations, requests, chargers, 50) == []
