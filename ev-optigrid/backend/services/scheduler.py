"""
Background tasks (synopsis stack: APScheduler).

Keeps the ML forecasters trained so the first API call isn't slow: one warm-up shortly after startup, then a
periodic check. Runs in a daemon thread inside the API process; set ENABLE_SCHEDULER=false to turn it off.
"""
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for ml/

from apscheduler.schedulers.background import BackgroundScheduler

log = logging.getLogger("evoptigrid.scheduler")
_scheduler: BackgroundScheduler | None = None


def warm_models() -> dict[str, bool | None]:
    """Trains any forecaster with no saved model. True = trained now, False = already there, None = failed."""
    from ml import grid_forecaster, price_forecaster, queue_predictor, solar_forecaster
    from ml.model_utils import ensure_trained

    result: dict[str, bool | None] = {}
    for name, module in (("price", price_forecaster), ("grid", grid_forecaster),
                         ("solar", solar_forecaster), ("queue", queue_predictor)):
        try:
            result[name] = ensure_trained(module)
        except Exception:  # noqa: BLE001 - a failed warm-up must never take the API down
            log.exception("warm-up failed for %s forecaster", name)
            result[name] = None
    log.info("model warm-up finished: %s", result)
    return result


def start_scheduler(enabled: bool = True, warm_interval_minutes: int = 60) -> BackgroundScheduler | None:
    global _scheduler
    if not enabled:
        return None
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(warm_models, "date", run_date=datetime.now() + timedelta(seconds=1), id="warm_models_startup")
    scheduler.add_job(warm_models, "interval", minutes=warm_interval_minutes, id="warm_models_periodic",
                      max_instances=1, coalesce=True)
    scheduler.start()
    _scheduler = scheduler
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


def status() -> dict:
    running = bool(_scheduler and _scheduler.running)
    return {"running": running, "jobs": sorted(j.id for j in _scheduler.get_jobs()) if running else []}
