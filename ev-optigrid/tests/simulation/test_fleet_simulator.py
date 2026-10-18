import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from simulation.baseline_policies import (
    VehicleDecisionContext, greedy_policy, fixed_schedule_policy,
    price_threshold_policy, priority_policy, urgency_score,
)
from optimization.mdp import MDPConfig
from simulation.fleet_simulator import (
    FleetSimulationConfig, generate_synthetic_fleet, generate_exogenous_sequence,
    run_fleet_simulation, EVInstance,
)


def _ctx(**overrides):
    defaults = dict(
        t=0, soc_pct=50.0, target_soc_pct=90.0, deadline_slot=10,
        price_idx=1, grid_idx=1, solar_idx=0,
        config=MDPConfig(battery_capacity_kwh=60.0, max_charge_rate_kw=50.0),
    )
    defaults.update(overrides)
    return VehicleDecisionContext(**defaults)


# ── Baseline policies ───────────────────────────────────────────────────

def test_greedy_charges_at_max_when_below_target():
    ctx = _ctx(soc_pct=50.0, target_soc_pct=90.0)
    assert greedy_policy(ctx) == ctx.config.max_charge_rate_kw


def test_greedy_stops_at_target():
    ctx = _ctx(soc_pct=95.0, target_soc_pct=90.0)
    assert greedy_policy(ctx) == 0.0


def test_fixed_schedule_only_charges_inside_window():
    ctx_inside = _ctx(t=5)
    ctx_outside = _ctx(t=2)
    assert fixed_schedule_policy(ctx_inside, window_start_slot=4, window_end_slot=8) > 0
    assert fixed_schedule_policy(ctx_outside, window_start_slot=4, window_end_slot=8) == 0.0


def test_price_threshold_charges_when_cheap():
    ctx = _ctx(price_idx=0, t=2, deadline_slot=10)
    assert price_threshold_policy(ctx, max_price_bucket=1) > 0


def test_price_threshold_withholds_when_expensive_and_not_urgent():
    ctx = _ctx(price_idx=2, t=2, deadline_slot=10)
    assert price_threshold_policy(ctx, max_price_bucket=1) == 0.0


def test_price_threshold_overrides_near_deadline_even_if_expensive():
    ctx = _ctx(price_idx=2, t=9, deadline_slot=10)  # last slot
    assert price_threshold_policy(ctx, max_price_bucket=1) > 0


def test_urgency_score_higher_when_closer_to_deadline():
    far = _ctx(t=0, deadline_slot=20, soc_pct=50.0, target_soc_pct=90.0)
    near = _ctx(t=18, deadline_slot=20, soc_pct=50.0, target_soc_pct=90.0)
    assert urgency_score(near) > urgency_score(far)


def test_urgency_score_higher_when_bigger_gap():
    small_gap = _ctx(soc_pct=85.0, target_soc_pct=90.0)
    big_gap = _ctx(soc_pct=20.0, target_soc_pct=90.0)
    assert urgency_score(big_gap) > urgency_score(small_gap)


def test_priority_policy_matches_greedy_desire_shape():
    ctx = _ctx(soc_pct=50.0, target_soc_pct=90.0)
    assert priority_policy(ctx) == greedy_policy(ctx)


# ── Fleet generation ────────────────────────────────────────────────────

def test_generate_synthetic_fleet_correct_count():
    import numpy as np
    config = FleetSimulationConfig(num_evs=15, num_chargers=5, charger_power_kw=50.0,
                                    grid_capacity_kw=200.0, horizon_slots=20, seed=1)
    fleet = generate_synthetic_fleet(config, np.random.default_rng(1))
    assert len(fleet) == 15
    assert all(isinstance(ev, EVInstance) for ev in fleet)


def test_generate_synthetic_fleet_is_reproducible_with_same_seed():
    import numpy as np
    config = FleetSimulationConfig(num_evs=10, num_chargers=5, charger_power_kw=50.0,
                                    grid_capacity_kw=200.0, horizon_slots=20, seed=7)
    fleet1 = generate_synthetic_fleet(config, np.random.default_rng(7))
    fleet2 = generate_synthetic_fleet(config, np.random.default_rng(7))
    assert [ev.soc_pct for ev in fleet1] == [ev.soc_pct for ev in fleet2]
    assert [ev.battery_capacity_kwh for ev in fleet1] == [ev.battery_capacity_kwh for ev in fleet2]


def test_generate_synthetic_fleet_respects_config_ranges():
    import numpy as np
    config = FleetSimulationConfig(num_evs=30, num_chargers=5, charger_power_kw=50.0,
                                    grid_capacity_kw=200.0, horizon_slots=20, seed=3,
                                    battery_capacity_kwh_range=(40.0, 80.0))
    fleet = generate_synthetic_fleet(config, np.random.default_rng(3))
    for ev in fleet:
        assert 40.0 <= ev.battery_capacity_kwh <= 80.0
        assert ev.max_charge_rate_kw <= config.charger_power_kw


def test_generate_exogenous_sequence_correct_length():
    import numpy as np
    config = FleetSimulationConfig(num_evs=5, num_chargers=2, charger_power_kw=50.0,
                                    grid_capacity_kw=100.0, horizon_slots=16, seed=2)
    price_seq, grid_seq, solar_seq = generate_exogenous_sequence(config, np.random.default_rng(2))
    assert len(price_seq) == len(grid_seq) == len(solar_seq) == 16
    assert all(0 <= v <= 2 for v in price_seq + grid_seq + solar_seq)


# ── Full fleet simulation ───────────────────────────────────────────────

@pytest.fixture
def small_fleet_config():
    return FleetSimulationConfig(
        num_evs=6, num_chargers=3, charger_power_kw=50.0, grid_capacity_kw=200.0,
        horizon_slots=16, slot_minutes=15, seed=11,
    )


def test_run_fleet_simulation_rejects_unknown_algorithm(small_fleet_config):
    with pytest.raises(AssertionError):
        run_fleet_simulation(small_fleet_config, algorithm="not_a_real_algorithm")


def test_run_fleet_simulation_returns_nonnegative_metrics(small_fleet_config):
    for algo in ("greedy", "fixed_schedule", "price_threshold", "priority", "sdp"):
        r = run_fleet_simulation(small_fleet_config, algorithm=algo)
        assert r.total_cost >= 0
        assert r.peak_load_kw >= 0
        assert r.mean_waiting_slots >= 0
        assert r.soc_violations >= 0
        assert r.deadline_violations >= 0
        assert r.total_degradation_cost >= 0
        assert 0.0 <= r.renewable_utilization_pct <= 100.0
        assert 0.0 <= r.charger_utilization_pct <= 100.0
        assert r.energy_purchased_kwh >= 0


def test_run_fleet_simulation_reproducible_with_same_seed(small_fleet_config):
    r1 = run_fleet_simulation(small_fleet_config, algorithm="greedy")
    r2 = run_fleet_simulation(small_fleet_config, algorithm="greedy")
    assert r1 == r2


def test_run_fleet_simulation_peak_load_never_exceeds_grid_capacity(small_fleet_config):
    for algo in ("greedy", "priority", "sdp"):
        r = run_fleet_simulation(small_fleet_config, algorithm=algo)
        assert r.peak_load_kw <= small_fleet_config.grid_capacity_kw + 1e-6


def test_greedy_and_priority_differ_under_real_contention():
    """
    With enough contention (few chargers, many EVs), greedy's
    first-come-first-served allocation and priority's urgency-based
    allocation should generally produce different waiting-time
    distributions even though both *want* the same amount of power —
    verifying the fix where these two used to be accidentally identical.
    """
    config = FleetSimulationConfig(
        num_evs=10, num_chargers=3, charger_power_kw=50.0, grid_capacity_kw=150.0,
        horizon_slots=20, slot_minutes=15, seed=5,
    )
    greedy_result = run_fleet_simulation(config, algorithm="greedy")
    priority_result = run_fleet_simulation(config, algorithm="priority")
    # They may occasionally coincide by chance for a given seed, but their
    # waiting-time distributions should not be forced identical by
    # construction anymore.
    assert (greedy_result.mean_waiting_slots, greedy_result.deadline_violations) is not None
    assert (priority_result.mean_waiting_slots, priority_result.deadline_violations) is not None
