import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from optimization.station_optimizer import (
    StationCandidate, COSWeights, resolve_cos_weights, compute_cos_scores,
    rank_stations, _minmax_goodness, COS_PROFILE_WEIGHTS,
)


def _station(id_, **overrides):
    defaults = dict(
        station_id=id_, name=id_, charging_cost=200.0, travel_time_min=10.0,
        distance_km=3.0, predicted_wait_min=5.0, charging_duration_min=40.0,
        battery_impact=0.3, grid_load_pct=60.0, renewable_availability=0.3,
        connector_availability_frac=0.5,
    )
    defaults.update(overrides)
    return StationCandidate(**defaults)


def test_minmax_goodness_lower_is_better():
    scores = _minmax_goodness([10, 20, 30], higher_is_better=False)
    assert scores[0] == 1.0   # lowest value = best when lower is better
    assert scores[2] == 0.0


def test_minmax_goodness_higher_is_better():
    scores = _minmax_goodness([10, 20, 30], higher_is_better=True)
    assert scores[2] == 1.0
    assert scores[0] == 0.0


def test_minmax_goodness_handles_all_equal_values():
    scores = _minmax_goodness([5, 5, 5], higher_is_better=False)
    assert scores == [1.0, 1.0, 1.0]


def test_all_six_cos_profiles_exist():
    for name in ("save_money", "fastest", "battery_health", "green", "balanced", "custom"):
        assert name in COS_PROFILE_WEIGHTS


def test_compute_cos_scores_empty_candidates_returns_empty():
    assert compute_cos_scores([], resolve_cos_weights("balanced")) == {}


def test_compute_cos_scores_range_0_to_100():
    candidates = [_station("A", charging_cost=100), _station("B", charging_cost=300)]
    scores = compute_cos_scores(candidates, resolve_cos_weights("balanced"))
    for v in scores.values():
        assert 0.0 <= v <= 100.0


def test_cheaper_station_scores_higher_under_save_money_profile():
    cheap = _station("cheap", charging_cost=100.0)
    expensive = _station("expensive", charging_cost=400.0)
    scores = compute_cos_scores([cheap, expensive], resolve_cos_weights("save_money"))
    assert scores["cheap"] > scores["expensive"]


def test_closer_faster_station_scores_higher_under_fastest_profile():
    fast = _station("fast", travel_time_min=2.0, charging_duration_min=15.0, predicted_wait_min=0.0)
    slow = _station("slow", travel_time_min=20.0, charging_duration_min=60.0, predicted_wait_min=20.0)
    scores = compute_cos_scores([fast, slow], resolve_cos_weights("fastest"))
    assert scores["fast"] > scores["slow"]


def test_more_renewable_station_scores_higher_under_green_profile():
    green_station = _station("green_one", renewable_availability=0.9)
    dirty_station = _station("dirty_one", renewable_availability=0.05)
    scores = compute_cos_scores([green_station, dirty_station], resolve_cos_weights("green"))
    assert scores["green_one"] > scores["dirty_one"]


def test_lower_battery_impact_scores_higher_under_battery_health_profile():
    gentle = _station("gentle", battery_impact=0.1)
    harsh = _station("harsh", battery_impact=0.8)
    scores = compute_cos_scores([gentle, harsh], resolve_cos_weights("battery_health"))
    assert scores["gentle"] > scores["harsh"]


def test_rank_stations_sorted_best_first():
    candidates = [_station("A", charging_cost=300), _station("B", charging_cost=100), _station("C", charging_cost=200)]
    ranked = rank_stations(candidates, profile="save_money")
    scores_in_order = [score for _, score in ranked]
    assert scores_in_order == sorted(scores_in_order, reverse=True)
    assert ranked[0][0].station_id == "B"  # cheapest wins under save_money


def test_profile_switch_changes_winner():
    """The same candidate set should be able to produce a DIFFERENT #1 pick
    depending on profile — the core requirement that weights actually
    matter for station selection, not just charging rate."""
    cheap_but_slow = _station("cheap_slow", charging_cost=100.0, travel_time_min=25.0,
                               charging_duration_min=70.0, predicted_wait_min=25.0)
    pricey_but_fast = _station("pricey_fast", charging_cost=500.0, travel_time_min=2.0,
                                charging_duration_min=15.0, predicted_wait_min=0.0)
    candidates = [cheap_but_slow, pricey_but_fast]

    save_money_winner = rank_stations(candidates, profile="save_money")[0][0].station_id
    fastest_winner = rank_stations(candidates, profile="fastest")[0][0].station_id
    assert save_money_winner == "cheap_slow"
    assert fastest_winner == "pricey_fast"


def test_custom_overrides_applied_to_cos_weights():
    weights = resolve_cos_weights("custom", custom_overrides={"w_cost": 9.9})
    assert weights.w_cost == 9.9
