"""
Trip energy-demand predictor (Phase 8, spec §10.C).

Predicts a journey's total energy requirement from distance, vehicle
efficiency, traffic conditions, and elevation gain. This is the ML-based
refinement layered on top of the simple physics estimate in
`services/journey_service.py`'s energy model (Phase 11) — the physics model
gives a fast, always-available baseline; this model can improve on it once
enough real trip data (`journeys`/`routes`) has accumulated to train on.
"""
from pathlib import Path

import joblib
import numpy as np

from ml.data_synthesis import generate_trip_demand_dataset
from ml.model_utils import train_and_evaluate_all, best_model, print_results, atomic_dump

FEATURE_COLUMNS = ["distance_km", "efficiency_kwh_per_km", "traffic_multiplier", "elevation_gain_m"]
ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "demand_predictor.joblib"


def prepare_dataset(n_samples: int = 3000, seed: int = 4):
    df = generate_trip_demand_dataset(n_samples=n_samples, seed=seed)
    X = df[FEATURE_COLUMNS].to_numpy()
    y = df["energy_required_kwh"].to_numpy()
    return X, y, df


def train(n_samples: int = 3000, seed: int = 4, save: bool = True):
    X, y, df = prepare_dataset(n_samples=n_samples, seed=seed)
    results = train_and_evaluate_all(X, y, seed=seed)
    print_results(results, target_name="trip energy requirement (kWh)")
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


def predict(distance_km: float, efficiency_kwh_per_km: float,
            traffic_multiplier: float = 1.0, elevation_gain_m: float = 0.0) -> float:
    bundle = load_model()
    model = bundle["model"]
    features = np.array([[distance_km, efficiency_kwh_per_km, traffic_multiplier, elevation_gain_m]])
    return max(0.0, float(model.predict(features)[0]))
