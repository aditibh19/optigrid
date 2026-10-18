"""
Charger queue predictor (Phase 8/11, spec §10.E and §11).

Predicts expected queue length at a station given time-of-day, day-of-week,
station capacity, and station popularity — the inputs `station_service`
(Phase 12) would derive from `station_demand` history and the station's
own recorded capacity. Used to compute `predicted_waiting_time` and feed
the Charging Opportunity Score's queue term (`optimization/station_optimizer.py`).
"""
from pathlib import Path

import joblib
import numpy as np

from ml.data_synthesis import generate_station_demand_series
from ml.model_utils import train_and_evaluate_all, best_model, print_results, atomic_dump

FEATURE_COLUMNS = ["hour_sin", "hour_cos", "weekday", "is_weekend", "station_capacity", "station_popularity"]
ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "queue_predictor.joblib"

# Average time (minutes) a vehicle occupies a charger — used to convert a
# predicted queue length into a predicted waiting time. Illustrative
# default; a real deployment would derive this from actual session
# durations in `charging_sessions`.
AVG_SESSION_MINUTES = 35.0


def prepare_dataset(n_stations: int = 8, n_days: int = 30, seed: int = 3):
    df = generate_station_demand_series(n_stations=n_stations, n_days=n_days, seed=seed)
    X = df[FEATURE_COLUMNS].to_numpy()
    y = df["queue_length"].to_numpy()
    return X, y, df


def train(n_stations: int = 8, n_days: int = 30, seed: int = 3, save: bool = True):
    X, y, df = prepare_dataset(n_stations=n_stations, n_days=n_days, seed=seed)
    results = train_and_evaluate_all(X, y, seed=seed)
    print_results(results, target_name="station queue length (vehicles)")
    winner = best_model(results)
    if save:
        ARTIFACT_PATH.parent.mkdir(exist_ok=True)
        atomic_dump({"model": winner.model, "feature_columns": FEATURE_COLUMNS,
                     "model_name": winner.model_name, "metrics": {
                         "mae": winner.mae, "rmse": winner.rmse, "r2": winner.r2}}, ARTIFACT_PATH)
    return results, winner


def load_model():
    if not ARTIFACT_PATH.exists():
        raise FileNotFoundError(f"No trained model at {ARTIFACT_PATH} — run train() first.")
    return joblib.load(ARTIFACT_PATH)


def predict_queue_and_wait(hour: int, weekday: int, station_capacity: int, station_popularity: float) -> dict:
    bundle = load_model()
    model = bundle["model"]
    features = np.array([[
        np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24),
        weekday, 1 if weekday >= 5 else 0,
        station_capacity, station_popularity,
    ]])
    predicted_queue = max(0.0, float(model.predict(features)[0]))
    predicted_wait_min = predicted_queue * AVG_SESSION_MINUTES / max(1, station_capacity)
    # Rough availability probability: drops as the predicted queue grows
    # relative to capacity (illustrative logistic-style curve, not fit to data).
    availability_probability = 1.0 / (1.0 + np.exp(predicted_queue - station_capacity / 2))
    return {
        "predicted_queue": round(predicted_queue, 2),
        "predicted_wait_min": round(predicted_wait_min, 1),
        "availability_probability": round(float(availability_probability), 3),
    }
