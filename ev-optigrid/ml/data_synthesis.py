"""
Synthetic data generation for the ML forecasting layer (Phase 8, spec §10).

SYNTHETIC per spec §10/§29 — every dataset produced here is generated, not
real, and every consumer of it is expected to label results accordingly.
Real deployments replace this module's outputs with actual historical rows
from `electricity_prices` / `grid_load` / `solar_generation` /
`station_demand` (backend/models/energy.py) once enough have accumulated.

Each generator produces a plausible daily/weekly seasonal pattern plus
noise — realistic enough to make the forecasting models' metrics meaningful
(a model trained on pure noise would show ~0 R², which would be a red flag,
not a good sign, that the synthetic data generator itself is broken).
"""
import numpy as np
import pandas as pd


def _time_features(timestamps: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({
        "hour": timestamps.hour,
        "hour_sin": np.sin(2 * np.pi * timestamps.hour / 24),
        "hour_cos": np.cos(2 * np.pi * timestamps.hour / 24),
        "weekday": timestamps.weekday,
        "is_weekend": (timestamps.weekday >= 5).astype(int),
    }, index=timestamps)


def generate_price_series(n_days: int = 60, freq_minutes: int = 15, seed: int = 0) -> pd.DataFrame:
    """
    Synthetic electricity price (₹/kWh): a daily double-peak pattern (morning
    + evening demand peaks) plus weekday/weekend differences and noise.
    """
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range("2026-01-01", periods=n_days * 24 * 60 // freq_minutes, freq=f"{freq_minutes}min")
    feats = _time_features(timestamps)

    base = 8.0
    morning_peak = 3.0 * np.exp(-((feats["hour"] - 9) ** 2) / (2 * 2.0 ** 2))
    evening_peak = 4.5 * np.exp(-((feats["hour"] - 19) ** 2) / (2 * 2.5 ** 2))
    weekend_discount = np.where(feats["is_weekend"] == 1, -1.0, 0.0)
    noise = rng.normal(0, 0.6, size=len(timestamps))

    price = base + morning_peak + evening_peak + weekend_discount + noise
    price = np.clip(price, 2.5, 20.0)

    df = feats.copy()
    df["timestamp"] = timestamps
    df["price_per_kwh"] = price
    # Lag features — yesterday's price at the same time-of-day is a strong predictor.
    steps_per_day = 24 * 60 // freq_minutes
    df["price_lag_1"] = df["price_per_kwh"].shift(1).bfill()
    df["price_lag_day"] = df["price_per_kwh"].shift(steps_per_day).bfill()
    return df.reset_index(drop=True)


def generate_grid_load_series(n_days: int = 60, freq_minutes: int = 15, seed: int = 1) -> pd.DataFrame:
    """Synthetic grid load (% of capacity): correlated with price's demand peaks, plus its own noise."""
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range("2026-01-01", periods=n_days * 24 * 60 // freq_minutes, freq=f"{freq_minutes}min")
    feats = _time_features(timestamps)

    base = 45.0
    morning_peak = 15.0 * np.exp(-((feats["hour"] - 9) ** 2) / (2 * 2.0 ** 2))
    evening_peak = 25.0 * np.exp(-((feats["hour"] - 19) ** 2) / (2 * 2.5 ** 2))
    weekend_discount = np.where(feats["is_weekend"] == 1, -8.0, 0.0)
    noise = rng.normal(0, 4.0, size=len(timestamps))

    load = base + morning_peak + evening_peak + weekend_discount + noise
    load = np.clip(load, 10.0, 98.0)

    df = feats.copy()
    df["timestamp"] = timestamps
    df["load_pct"] = load
    steps_per_day = 24 * 60 // freq_minutes
    df["load_lag_1"] = df["load_pct"].shift(1).bfill()
    df["load_lag_day"] = df["load_pct"].shift(steps_per_day).bfill()
    return df.reset_index(drop=True)


def generate_solar_series(n_days: int = 60, freq_minutes: int = 15, seed: int = 2,
                           max_generation_kwh: float = 8.0) -> pd.DataFrame:
    """Synthetic solar generation: zero at night, a smooth midday bell curve, clipped at zero, plus cloud noise."""
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range("2026-01-01", periods=n_days * 24 * 60 // freq_minutes, freq=f"{freq_minutes}min")
    feats = _time_features(timestamps)

    daylight = np.clip(np.sin(np.pi * (feats["hour"] - 6) / 12), 0, None)  # 0 outside 6am-6pm, bell inside
    # Random daily "cloudiness" factor per calendar day so entire days can be dimmer.
    day_index = (timestamps - timestamps[0]).days
    n_unique_days = day_index.max() + 1
    cloud_factor_per_day = rng.uniform(0.5, 1.0, size=n_unique_days)
    cloud_factor = cloud_factor_per_day[day_index]

    generation = max_generation_kwh * daylight * cloud_factor
    generation += rng.normal(0, 0.15, size=len(timestamps))
    generation = np.clip(generation, 0.0, max_generation_kwh)

    df = feats.copy()
    df["timestamp"] = timestamps
    df["generation_kwh"] = generation
    steps_per_day = 24 * 60 // freq_minutes
    df["generation_lag_day"] = df["generation_kwh"].shift(steps_per_day).bfill()
    return df.reset_index(drop=True)


def generate_station_demand_series(n_stations: int = 5, n_days: int = 30, freq_minutes: int = 30,
                                    seed: int = 3, station_capacity: int = 3) -> pd.DataFrame:
    """
    Synthetic per-station occupancy history: active session count and queue
    length, following a commuter-style daily pattern (busiest at morning and
    evening) with per-station popularity variation.

    `station_capacity=3` (deliberately lower than an earlier draft's 4)
    ensures demand regularly exceeds capacity during peak hours — with a
    higher capacity, queue_length was almost always 0 and the queue
    predictor had nothing real to learn (R² near zero, since predicting
    "always 0" already minimizes error on a near-constant target). This is
    itself worth knowing for the viva: an ML model's poor score can be a
    sign the *data generator* doesn't produce the phenomenon being
    predicted, not necessarily a modeling failure.
    """
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range("2026-01-01", periods=n_days * 24 * 60 // freq_minutes, freq=f"{freq_minutes}min")
    feats = _time_features(timestamps)

    rows = []
    station_popularity = rng.uniform(0.6, 1.6, size=n_stations)
    for station_id in range(n_stations):
        morning_peak = 3.0 * np.exp(-((feats["hour"] - 9) ** 2) / (2 * 1.5 ** 2))
        evening_peak = 4.5 * np.exp(-((feats["hour"] - 18) ** 2) / (2 * 2.0 ** 2))
        base_demand = (1.2 + morning_peak + evening_peak) * station_popularity[station_id]
        noise = rng.normal(0, 0.6, size=len(timestamps))
        demand = np.clip(base_demand + noise, 0, None)

        active_sessions = np.clip(np.round(demand), 0, station_capacity).astype(int)
        queue_length = np.clip(np.round(demand - station_capacity), 0, None).astype(int)

        station_df = feats.copy()
        station_df["timestamp"] = timestamps
        station_df["station_id"] = station_id
        station_df["active_sessions"] = active_sessions
        station_df["queue_length"] = queue_length
        station_df["station_capacity"] = station_capacity
        station_df["station_popularity"] = station_popularity[station_id]
        rows.append(station_df)

    return pd.concat(rows, ignore_index=True)


def generate_trip_demand_dataset(n_samples: int = 3000, seed: int = 4) -> pd.DataFrame:
    """
    Synthetic (distance, vehicle efficiency, traffic) -> energy_required
    dataset for the trip/demand predictor. The "true" relationship is
    linear-with-traffic-multiplier plus noise, which is what the model is
    expected to recover.
    """
    rng = np.random.default_rng(seed)
    distance_km = rng.uniform(2, 400, size=n_samples)
    efficiency_kwh_per_km = rng.uniform(0.12, 0.22, size=n_samples)
    traffic_multiplier = rng.uniform(1.0, 1.6, size=n_samples)
    elevation_gain_m = rng.uniform(0, 800, size=n_samples)

    energy_kwh = (
        distance_km * efficiency_kwh_per_km * traffic_multiplier
        + elevation_gain_m * 0.00025  # small additional cost per meter climbed
        + rng.normal(0, 0.8, size=n_samples)
    )
    energy_kwh = np.clip(energy_kwh, 0.1, None)

    return pd.DataFrame({
        "distance_km": distance_km,
        "efficiency_kwh_per_km": efficiency_kwh_per_km,
        "traffic_multiplier": traffic_multiplier,
        "elevation_gain_m": elevation_gain_m,
        "energy_required_kwh": energy_kwh,
    })
