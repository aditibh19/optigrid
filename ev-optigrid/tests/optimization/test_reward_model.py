import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from optimization.reward_model import (
    step_cost, terminal_cost, resolve_weights, real_electricity_cost,
    PROFILE_WEIGHTS, ProfileWeights,
)


def test_all_six_profiles_exist():
    for name in ("save_money", "fastest", "battery_health", "green", "balanced", "custom"):
        assert name in PROFILE_WEIGHTS


def test_step_cost_zero_action_has_zero_electricity_and_grid_cost():
    weights = resolve_weights("balanced")
    cost = step_cost(
        soc_before_pct=50.0, soc_after_pct=50.0, action_kw=0.0, max_charge_rate_kw=50.0,
        price_idx=2, grid_idx=2, solar_idx=0, slot_hours=0.5, weights=weights,
    )
    # No charging => no electricity/degradation/grid cost, no renewable reward => cost should be 0
    assert cost == pytest.approx(0.0)


def test_step_cost_increases_with_price_for_same_action():
    weights = resolve_weights("save_money")
    cheap = step_cost(50.0, 55.0, 10.0, 50.0, price_idx=0, grid_idx=1, solar_idx=0,
                       slot_hours=0.5, weights=weights)
    expensive = step_cost(50.0, 55.0, 10.0, 50.0, price_idx=2, grid_idx=1, solar_idx=0,
                           slot_hours=0.5, weights=weights)
    assert expensive > cheap


def test_step_cost_lower_with_solar_available_due_to_renewable_reward():
    weights = resolve_weights("green")
    no_solar = step_cost(50.0, 60.0, 20.0, 50.0, price_idx=1, grid_idx=1, solar_idx=0,
                          slot_hours=0.5, weights=weights)
    with_solar = step_cost(50.0, 60.0, 20.0, 50.0, price_idx=1, grid_idx=1, solar_idx=2,
                            slot_hours=0.5, weights=weights)
    assert with_solar < no_solar


def test_step_cost_save_money_more_price_sensitive_than_fastest():
    save_money_w = resolve_weights("save_money")
    fastest_w = resolve_weights("fastest")
    delta_save_money = (
        step_cost(50, 55, 10, 50, 2, 1, 0, 0.5, save_money_w)
        - step_cost(50, 55, 10, 50, 0, 1, 0, 0.5, save_money_w)
    )
    delta_fastest = (
        step_cost(50, 55, 10, 50, 2, 1, 0, 0.5, fastest_w)
        - step_cost(50, 55, 10, 50, 0, 1, 0, 0.5, fastest_w)
    )
    assert delta_save_money > delta_fastest


def test_terminal_cost_zero_when_target_met():
    weights = resolve_weights("balanced")
    cost = terminal_cost(final_soc_pct=90.0, target_soc_pct=90.0, minimum_safe_soc_pct=70.0, weights=weights)
    assert cost == pytest.approx(0.0)


def test_terminal_cost_positive_when_target_missed():
    weights = resolve_weights("balanced")
    cost = terminal_cost(final_soc_pct=60.0, target_soc_pct=90.0, minimum_safe_soc_pct=70.0, weights=weights)
    assert cost > 0.0


def test_terminal_cost_penalizes_deadline_violation_more_than_mere_unmet_target():
    weights = resolve_weights("balanced")
    only_unmet = terminal_cost(final_soc_pct=75.0, target_soc_pct=90.0, minimum_safe_soc_pct=70.0, weights=weights)
    below_min_safe = terminal_cost(final_soc_pct=60.0, target_soc_pct=90.0, minimum_safe_soc_pct=70.0, weights=weights)
    assert below_min_safe > only_unmet


def test_resolve_weights_custom_overrides_applied():
    overrides = {"w_cost": 9.9}
    weights = resolve_weights("custom", custom_overrides=overrides)
    assert weights.w_cost == 9.9


def test_resolve_weights_custom_without_overrides_falls_back_to_balanced_values():
    weights = resolve_weights("custom", custom_overrides=None)
    assert weights.w_cost == PROFILE_WEIGHTS["custom"].w_cost


def test_resolve_weights_unknown_profile_falls_back_to_balanced():
    weights = resolve_weights("not_a_real_profile")
    assert weights == PROFILE_WEIGHTS["balanced"]


def test_real_electricity_cost_matches_simple_multiplication():
    cost = real_electricity_cost(action_kw=10.0, price_idx=1, slot_hours=0.5)
    assert cost == pytest.approx(10.0 * 0.5 * 8.0)  # medium price = 8.0 in defaults
