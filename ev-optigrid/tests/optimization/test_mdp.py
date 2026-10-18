import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from optimization.mdp import (
    MDPConfig, N_SOC, nearest_soc_bucket_index, soc_from_bucket_index,
    bucketize_price, bucketize_grid_load, bucketize_solar,
)


def test_soc_bucket_roundtrip_at_grid_points():
    for pct in (0.0, 5.0, 50.0, 95.0, 100.0):
        idx = nearest_soc_bucket_index(pct)
        assert soc_from_bucket_index(idx) == pytest.approx(pct)


def test_soc_bucket_rounds_to_nearest():
    # 47 should round to bucket for 45 (nearest multiple of 5)
    idx = nearest_soc_bucket_index(47.0)
    assert soc_from_bucket_index(idx) == pytest.approx(45.0)


def test_soc_bucket_index_clamped_to_valid_range():
    assert nearest_soc_bucket_index(-10.0) == 0
    assert nearest_soc_bucket_index(150.0) == N_SOC - 1


def test_bucketize_price_low_medium_high():
    assert bucketize_price(3.0) == 0
    assert bucketize_price(8.0) == 1
    assert bucketize_price(15.0) == 2


def test_bucketize_grid_load():
    assert bucketize_grid_load(20.0) == 0
    assert bucketize_grid_load(60.0) == 1
    assert bucketize_grid_load(95.0) == 2


def test_bucketize_solar():
    assert bucketize_solar(0.0) == 0
    assert bucketize_solar(0.3) == 1
    assert bucketize_solar(0.9) == 2


def test_mdp_config_feasible_actions_respects_max_rate():
    config = MDPConfig(battery_capacity_kwh=60.0, max_charge_rate_kw=20.0)
    feasible = config.feasible_actions_kw()
    assert max(feasible) <= 20.0
    assert 0.0 in feasible


def test_mdp_config_feasible_actions_never_empty_even_if_max_rate_tiny():
    config = MDPConfig(battery_capacity_kwh=60.0, max_charge_rate_kw=0.0)
    feasible = config.feasible_actions_kw()
    assert feasible == (0.0,)


def test_soc_gain_pct_scales_with_power_and_time():
    config = MDPConfig(battery_capacity_kwh=60.0, max_charge_rate_kw=50.0,
                        charging_efficiency=1.0, slot_minutes=60)
    # 10kW for 1 hour = 10kWh into a 60kWh battery = ~16.67 percentage points
    gain = config.soc_gain_pct(10.0)
    assert gain == pytest.approx(100.0 * 10.0 / 60.0)


def test_soc_gain_pct_zero_for_zero_action():
    config = MDPConfig(battery_capacity_kwh=60.0, max_charge_rate_kw=50.0)
    assert config.soc_gain_pct(0.0) == 0.0
