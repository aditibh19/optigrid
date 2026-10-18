"""Solar generation forecaster (Phase 8, spec §10.D). Same structure as price_forecaster.py."""
from pathlib import Path

import joblib
import numpy as np

from ml.data_synthesis import generate_solar_series
from ml.model_utils import train_and_evaluate_all, best_model, print_results, atomic_dump

FEATURE_COLUMNS = ["hour_sin", "hour_cos", "weekday", "is_weekend", "generation_lag_day"]
ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "solar_forecaster.joblib"


def prepare_dataset(n_days: int = 60, seed: int = 2):
    df = generate_solar_series(n_days=n_days, seed=seed)
    X = df[FEATURE_COLUMNS].to_numpy()
    y = df["generation_kwh"].to_numpy()
    return X, y, df


def train(n_days: int = 60, seed: int = 2, save: bool = True):
    X, y, df = prepare_dataset(n_days=n_days, seed=seed)
    results = train_and_evaluate_all(X, y, seed=seed)
    print_results(results, target_name="solar generation (kWh)")
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


def predict(hour: int, weekday: int, generation_yesterday_same_time: float) -> float:
    bundle = load_model()
    model = bundle["model"]
    features = np.array([[
        np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24),
        weekday, 1 if weekday >= 5 else 0,
        generation_yesterday_same_time,
    ]])
    return max(0.0, float(model.predict(features)[0]))
