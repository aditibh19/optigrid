"""
Shared model training + evaluation utility (Phase 8, spec §10).

Trains all three requested model families (XGBoost, Random Forest, Gradient
Boosting) on the same train/test split and reports real MAE/RMSE/R² on a
held-out test set for each — never fabricated (spec §10: "Do not fabricate
metrics"). If xgboost isn't installed in the environment, it's swapped for
scikit-learn's HistGradientBoostingRegressor (a very similar gradient-
boosting implementation) and clearly labeled as a substitute, rather than
silently pretending XGBoost ran.
"""
import os
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import joblib

import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

try:
    from xgboost import XGBRegressor
    _XGBOOST_AVAILABLE = True
except Exception:  # noqa: BLE001
    # ImportError if the package is missing, but ALSO xgboost.core.XGBoostError when it is installed
    # yet its native library can't load (typical on macOS without `brew install libomp`).
    # Either way, fall back to scikit-learn's gradient boosting and say so, instead of crashing the API at import.
    _XGBOOST_AVAILABLE = False


@dataclass
class ModelEvalResult:
    model_name: str
    model: object
    mae: float
    rmse: float
    r2: float
    is_substitute: bool = False  # True if this stood in for an unavailable library


def time_based_split(n_rows: int, test_fraction: float = 0.2) -> tuple:
    """
    For time series, a random split would leak future information into
    training (a lagged feature computed from a "future" row could end up
    training a model to predict rows that come chronologically before it).
    Splitting on a contiguous trailing block avoids that.
    """
    split_at = int(n_rows * (1 - test_fraction))
    return np.arange(split_at), np.arange(split_at, n_rows)


def _build_candidate_models(seed: int) -> dict:
    models = {
        "random_forest": RandomForestRegressor(n_estimators=200, max_depth=8, random_state=seed, n_jobs=-1),
        "gradient_boosting": GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=seed),
    }
    if _XGBOOST_AVAILABLE:
        models["xgboost"] = XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.05,
                                          random_state=seed, verbosity=0)
    else:
        models["xgboost (substitute: HistGradientBoosting)"] = HistGradientBoostingRegressor(
            max_iter=200, max_depth=4, learning_rate=0.05, random_state=seed)
    return models


def train_and_evaluate_all(X: np.ndarray, y: np.ndarray, seed: int = 42) -> list[ModelEvalResult]:
    """Trains every candidate model on the same split, returns real held-out metrics for each."""
    train_idx, test_idx = time_based_split(len(X))
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    results = []
    for name, model in _build_candidate_models(seed).items():
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
        r2 = r2_score(y_test, preds)
        results.append(ModelEvalResult(
            model_name=name, model=model, mae=round(mae, 4), rmse=round(rmse, 4), r2=round(r2, 4),
            is_substitute=("substitute" in name),
        ))
    return results


def best_model(results: list[ModelEvalResult]) -> ModelEvalResult:
    """Lowest RMSE on the held-out test set wins — not hardcoded, computed from the results list."""
    return min(results, key=lambda r: r.rmse)


def print_results(results: list[ModelEvalResult], target_name: str) -> None:
    print(f"  Model comparison for '{target_name}' (held-out test set):")
    for r in sorted(results, key=lambda r: r.rmse):
        flag = " [substitute for unavailable xgboost]" if r.is_substitute else ""
        print(f"    {r.model_name:40s} MAE={r.mae:8.4f}  RMSE={r.rmse:8.4f}  R²={r.r2:7.4f}{flag}")


def atomic_dump(obj, path) -> None:
    """joblib.dump via a temp file + os.replace, so a reader never sees a half-written model.

    (Writing straight to the final path left truncated files that crashed every later request;
    the same bug was found and fixed in optimization/policy.py.)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp{path.suffix}")
    try:
        joblib.dump(obj, tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


_TRAIN_LOCK = threading.Lock()


def ensure_trained(module) -> bool:
    """Trains `module` if it has no saved model. Safe to call from many threads: trains at most once.

    Returns True if this call trained the model. Used by the API (train on first use) and by the
    background scheduler (warm up at startup), which can otherwise race to train the same model.
    """
    with _TRAIN_LOCK:
        if module.ARTIFACT_PATH.exists():
            return False
        module.train()
        return True
