import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from optimization.battery_model import (
    depth_of_discharge_term, high_soc_exposure_term, high_charging_power_term,
    temperature_term, compute_degradation_cost, battery_health_indicator,
    BatteryDegradationWeights,
)


def test_depth_of_discharge_zero_when_no_change():
    assert depth_of_discharge_term(50.0, 50.0) == 0.0


def test_depth_of_discharge_increases_with_swing():
    small = depth_of_discharge_term(50.0, 60.0)
    large = depth_of_discharge_term(20.0, 90.0)
    assert large > small


def test_high_soc_exposure_zero_below_threshold():
    assert high_soc_exposure_term(70.0, threshold=80.0) == 0.0


def test_high_soc_exposure_positive_above_threshold():
    assert high_soc_exposure_term(95.0, threshold=80.0) > 0.0


def test_high_soc_exposure_bounded_at_one():
    assert high_soc_exposure_term(100.0, threshold=80.0) == 1.0


def test_charging_rate_term_scales_with_power():
    low = high_charging_power_term(10.0, max_charge_rate_kw=50.0)
    high = high_charging_power_term(50.0, max_charge_rate_kw=50.0)
    assert 0.0 <= low < high <= 1.0


def test_charging_rate_term_handles_zero_max_rate():
    assert high_charging_power_term(10.0, max_charge_rate_kw=0.0) == 0.0


def test_temperature_term_zero_when_absent():
    assert temperature_term(None) == 0.0


def test_temperature_term_penalizes_extremes():
    ideal = temperature_term(20.0)
    extreme = temperature_term(45.0)
    assert extreme > ideal


def test_degradation_cost_is_nonnegative_and_bounded_ish():
    cost = compute_degradation_cost(
        soc_before=20.0, soc_after=95.0, charge_power_kw=50.0, max_charge_rate_kw=50.0,
    )
    assert cost >= 0.0
    # sum of weights is 1.0 (0.30+0.25+0.35+0.10), so worst case each term at 1.0 -> cost <= 1.0
    assert cost <= 1.0 + 1e-9


def test_degradation_cost_gentle_charging_is_cheaper():
    gentle = compute_degradation_cost(
        soc_before=40.0, soc_after=50.0, charge_power_kw=5.0, max_charge_rate_kw=50.0,
    )
    aggressive = compute_degradation_cost(
        soc_before=20.0, soc_after=95.0, charge_power_kw=50.0, max_charge_rate_kw=50.0,
    )
    assert gentle < aggressive


def test_battery_health_indicator_full_health_at_zero_cost():
    assert battery_health_indicator(0.0) == 100.0


def test_battery_health_indicator_decreases_with_cumulative_cost():
    h1 = battery_health_indicator(50.0, scale=500.0)
    h2 = battery_health_indicator(200.0, scale=500.0)
    assert h2 < h1


def test_battery_health_indicator_never_negative():
    assert battery_health_indicator(10_000.0, scale=500.0) == 0.0


def test_custom_weights_change_result():
    default_cost = compute_degradation_cost(30.0, 90.0, 40.0, 50.0)
    battery_focused = compute_degradation_cost(
        30.0, 90.0, 40.0, 50.0,
        weights=BatteryDegradationWeights(k_dod=0.1, k_high_soc=0.1, k_charge_rate=0.7, k_temperature=0.1),
    )
    assert default_cost != battery_focused
