import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pytest

from optimization.mdp import MDPConfig
from optimization.reward_model import resolve_weights
from optimization.transition_model import TransitionModel
from optimization.value_iteration import solve_value_iteration


@pytest.fixture
def small_config():
    return MDPConfig(
        battery_capacity_kwh=60.0, max_charge_rate_kw=50.0,
        slot_minutes=30, horizon_slots=6,
    )


def test_solve_produces_correctly_shaped_arrays(small_config):
    weights = resolve_weights("balanced")
    policy = solve_value_iteration(small_config, weights, target_soc_pct=90.0, minimum_safe_soc_pct=70.0)
    assert policy.V.shape[0] == small_config.horizon_slots + 1
    assert policy.policy.shape[0] == small_config.horizon_slots


def test_solve_no_nans_or_infs(small_config):
    weights = resolve_weights("balanced")
    policy = solve_value_iteration(small_config, weights, target_soc_pct=90.0, minimum_safe_soc_pct=70.0)
    assert np.all(np.isfinite(policy.V))


def test_policy_actions_are_within_feasible_set(small_config):
    weights = resolve_weights("balanced")
    policy = solve_value_iteration(small_config, weights, target_soc_pct=90.0, minimum_safe_soc_pct=70.0)
    valid_actions = set(policy.actions_kw)
    for t in range(small_config.horizon_slots):
        for soc_idx in range(policy.policy.shape[1]):
            a_idx = policy.policy[t, soc_idx, 0, 0, 0]
            assert policy.actions_kw[a_idx] in valid_actions


def test_full_soc_never_charges_further(small_config):
    """At 100% SOC there's nothing to gain — optimal action should be 0 kW
    in every exogenous state (charging past 100% wastes money/degrades battery
    for zero benefit, and the terminal cost is already satisfied)."""
    weights = resolve_weights("balanced")
    policy = solve_value_iteration(small_config, weights, target_soc_pct=90.0, minimum_safe_soc_pct=70.0)
    full_soc_idx = -1  # last bucket = 100%
    for t in range(small_config.horizon_slots):
        for p in range(3):
            for g in range(3):
                for s in range(3):
                    a_idx = policy.policy[t, full_soc_idx, p, g, s]
                    assert policy.actions_kw[a_idx] == 0.0


def test_lower_max_charge_rate_reduces_achievable_final_soc():
    weights = resolve_weights("balanced")
    fast_config = MDPConfig(battery_capacity_kwh=60.0, max_charge_rate_kw=50.0, slot_minutes=30, horizon_slots=4)
    slow_config = MDPConfig(battery_capacity_kwh=60.0, max_charge_rate_kw=7.0, slot_minutes=30, horizon_slots=4)

    fast_policy = solve_value_iteration(fast_config, weights, target_soc_pct=90.0, minimum_safe_soc_pct=70.0)
    slow_policy = solve_value_iteration(slow_config, weights, target_soc_pct=90.0, minimum_safe_soc_pct=70.0)

    def simulate(policy, config):
        soc = 30.0
        for t in range(config.horizon_slots):
            a = policy.action_kw(t, soc, 0, 0, 0)  # cheap price, low grid, no solar — always charge if useful
            soc = min(100.0, soc + config.soc_gain_pct(a))
        return soc

    assert simulate(fast_policy, fast_config) >= simulate(slow_policy, slow_config)


def test_value_function_at_target_soc_is_cheaper_than_far_below_target():
    weights = resolve_weights("balanced")
    config = MDPConfig(battery_capacity_kwh=60.0, max_charge_rate_kw=50.0, slot_minutes=30, horizon_slots=6)
    policy = solve_value_iteration(config, weights, target_soc_pct=90.0, minimum_safe_soc_pct=70.0)
    v_at_target = policy.value_at(0, 90.0, 1, 1, 1)
    v_far_below = policy.value_at(0, 20.0, 1, 1, 1)
    assert v_at_target <= v_far_below


def test_custom_transition_model_accepted():
    weights = resolve_weights("balanced")
    config = MDPConfig(battery_capacity_kwh=60.0, max_charge_rate_kw=50.0, slot_minutes=30, horizon_slots=4)
    tm = TransitionModel()
    policy = solve_value_iteration(config, weights, 90.0, 70.0, transition_model=tm)
    assert policy.V is not None
