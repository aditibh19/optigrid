import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pytest

from ml.data_synthesis import (
    generate_price_series, generate_grid_load_series, generate_solar_series,
    generate_station_demand_series, generate_trip_demand_dataset,
)
from ml.model_utils import train_and_evaluate_all, best_model, time_based_split


# ── Data synthesis sanity checks ────────────────────────────────────────

def test_price_series_within_plausible_bounds():
    df = generate_price_series(n_days=10)
    assert df["price_per_kwh"].min() >= 2.5
    assert df["price_per_kwh"].max() <= 20.0


def test_price_series_reproducible_with_seed():
    df1 = generate_price_series(n_days=5, seed=99)
    df2 = generate_price_series(n_days=5, seed=99)
    assert np.allclose(df1["price_per_kwh"], df2["price_per_kwh"])


def test_price_series_evening_pricier_than_night_on_average():
    df = generate_price_series(n_days=20, seed=1)
    evening = df[df["hour"].isin([18, 19, 20])]["price_per_kwh"].mean()
    night = df[df["hour"].isin([2, 3, 4])]["price_per_kwh"].mean()
    assert evening > night


def test_grid_load_within_bounds():
    df = generate_grid_load_series(n_days=10)
    assert df["load_pct"].min() >= 10.0
    assert df["load_pct"].max() <= 98.0


def test_solar_series_zero_at_night():
    df = generate_solar_series(n_days=5, seed=1)
    night = df[df["hour"].isin([0, 1, 2, 3])]
    assert night["generation_kwh"].max() < 0.5  # allow tiny noise


def test_solar_series_positive_at_midday():
    df = generate_solar_series(n_days=5, seed=1)
    midday = df[df["hour"] == 12]
    assert midday["generation_kwh"].mean() > 1.0


def test_station_demand_has_queue_variance():
    """Regression check for the R²≈0 bug: queue_length must have real variance,
    not be constant/near-constant."""
    df = generate_station_demand_series(n_stations=5, n_days=20)
    assert df["queue_length"].std() > 0.3
    assert df["queue_length"].max() > 0


def test_trip_demand_dataset_scales_with_distance():
    df = generate_trip_demand_dataset(n_samples=500, seed=1)
    short_trips = df[df["distance_km"] < 50]
    long_trips = df[df["distance_km"] > 300]
    assert long_trips["energy_required_kwh"].mean() > short_trips["energy_required_kwh"].mean()


# ── Model utilities ─────────────────────────────────────────────────────

def test_time_based_split_no_overlap_and_covers_all_rows():
    train_idx, test_idx = time_based_split(100, test_fraction=0.2)
    assert len(train_idx) == 80
    assert len(test_idx) == 20
    assert set(train_idx).isdisjoint(set(test_idx))
    assert max(train_idx) < min(test_idx)  # train is strictly before test in time


def test_train_and_evaluate_all_returns_all_three_families():
    rng = np.random.default_rng(0)
    X = rng.uniform(0, 10, size=(200, 3))
    y = X[:, 0] * 2 + X[:, 1] - X[:, 2] + rng.normal(0, 0.1, size=200)
    results = train_and_evaluate_all(X, y, seed=0)
    assert len(results) == 3
    names = [r.model_name for r in results]
    assert any("random_forest" in n for n in names)
    assert any("gradient_boosting" in n for n in names)
    assert any("xgboost" in n for n in names)


def test_train_and_evaluate_recovers_simple_linear_signal_well():
    """On an easy, low-noise linear relationship, every model should score
    reasonably well — this is a smoke test that the pipeline itself works."""
    rng = np.random.default_rng(1)
    X = rng.uniform(0, 10, size=(500, 2))
    y = 3 * X[:, 0] + 2 * X[:, 1] + rng.normal(0, 0.05, size=500)
    results = train_and_evaluate_all(X, y, seed=1)
    for r in results:
        assert r.r2 > 0.9, f"{r.model_name} scored r2={r.r2} on an easy signal"


def test_best_model_picks_lowest_rmse():
    rng = np.random.default_rng(2)
    X = rng.uniform(0, 10, size=(300, 2))
    y = X[:, 0] + rng.normal(0, 0.1, size=300)
    results = train_and_evaluate_all(X, y, seed=2)
    winner = best_model(results)
    assert winner.rmse == min(r.rmse for r in results)
