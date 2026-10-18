"""
ML forecast endpoints (Phase 12, spec §26). Thin wrappers around the
ml/*_forecaster.py modules — trains-on-first-use if no saved model exists
yet, then serves from the persisted artifact.
"""
import sys
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

router = APIRouter()


def _ensure_trained(module):
    from ml.model_utils import ensure_trained
    ensure_trained(module)


@router.get("/prices")
def predict_price(hour: int | None = None, weekday: int | None = None,
                   recent_price: float = 8.0, price_yesterday_same_time: float = 8.0):
    from ml import price_forecaster
    _ensure_trained(price_forecaster)
    now = datetime.utcnow()
    prediction = price_forecaster.predict(
        hour if hour is not None else now.hour, weekday if weekday is not None else now.weekday(),
        recent_price, price_yesterday_same_time,
    )
    return {"predicted_price_per_kwh": round(prediction, 2), "source": "predicted"}


@router.get("/grid")
def predict_grid(hour: int | None = None, weekday: int | None = None,
                  recent_load: float = 60.0, load_yesterday_same_time: float = 60.0):
    from ml import grid_forecaster
    _ensure_trained(grid_forecaster)
    now = datetime.utcnow()
    prediction = grid_forecaster.predict(
        hour if hour is not None else now.hour, weekday if weekday is not None else now.weekday(),
        recent_load, load_yesterday_same_time,
    )
    return {"predicted_grid_load_pct": round(prediction, 1), "source": "predicted"}


@router.get("/solar")
def predict_solar(hour: int | None = None, weekday: int | None = None, generation_yesterday_same_time: float = 3.0):
    from ml import solar_forecaster
    _ensure_trained(solar_forecaster)
    now = datetime.utcnow()
    prediction = solar_forecaster.predict(
        hour if hour is not None else now.hour, weekday if weekday is not None else now.weekday(),
        generation_yesterday_same_time,
    )
    return {"predicted_generation_kwh": round(prediction, 2), "source": "predicted"}


@router.get("/queue")
def predict_queue(station_capacity: int = 3, station_popularity: float = 1.0,
                   hour: int | None = None, weekday: int | None = None):
    from ml import queue_predictor
    _ensure_trained(queue_predictor)
    now = datetime.utcnow()
    result = queue_predictor.predict_queue_and_wait(
        hour if hour is not None else now.hour, weekday if weekday is not None else now.weekday(),
        station_capacity, station_popularity,
    )
    result["source"] = "predicted"
    return result
