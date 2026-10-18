"""Background scheduler + safe model training (ml/model_utils.ensure_trained / atomic_dump)."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import joblib
import pytest

from ml.model_utils import atomic_dump, ensure_trained


class FakeForecaster:
    def __init__(self, path):
        self.ARTIFACT_PATH = path
        self.calls = 0

    def train(self):
        time.sleep(0.05)               # widen the race window
        self.calls += 1
        atomic_dump({"model": "x"}, self.ARTIFACT_PATH)


def test_ensure_trained_trains_once_even_when_called_concurrently(tmp_path):
    fake = FakeForecaster(tmp_path / "m.joblib")
    results = []
    threads = [threading.Thread(target=lambda: results.append(ensure_trained(fake))) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert fake.calls == 1 and results.count(True) == 1 and results.count(False) == 7


def test_atomic_dump_roundtrips_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "sub" / "model.joblib"
    atomic_dump({"a": [1, 2, 3]}, target)
    assert joblib.load(target) == {"a": [1, 2, 3]}
    assert [p.name for p in target.parent.iterdir()] == ["model.joblib"]


def test_atomic_dump_failure_keeps_the_previous_model(tmp_path):
    target = tmp_path / "model.joblib"
    atomic_dump({"v": 1}, target)

    class Unpicklable:
        def __reduce__(self):
            raise RuntimeError("cannot pickle")

    with pytest.raises(Exception):
        atomic_dump(Unpicklable(), target)
    assert joblib.load(target) == {"v": 1}, "a failed save must not damage the existing model"
    assert [p.name for p in tmp_path.iterdir()] == ["model.joblib"]


def test_scheduler_starts_registers_jobs_and_stops():
    from services import scheduler
    s = scheduler.start_scheduler(enabled=True, warm_interval_minutes=600)
    try:
        assert scheduler.status()["running"] is True
        assert scheduler.status()["jobs"] == ["warm_models_periodic", "warm_models_startup"]
        assert scheduler.start_scheduler(enabled=True) is s, "starting twice must not create a second scheduler"
    finally:
        scheduler.stop_scheduler()
    assert scheduler.status() == {"running": False, "jobs": []}


def test_scheduler_can_be_disabled():
    from services import scheduler
    assert scheduler.start_scheduler(enabled=False) is None and scheduler.status()["running"] is False


def test_warm_models_reports_per_model_and_survives_a_failure(monkeypatch, tmp_path):
    from ml import grid_forecaster, price_forecaster, queue_predictor, solar_forecaster
    from services import scheduler
    for i, mod in enumerate((price_forecaster, grid_forecaster, solar_forecaster, queue_predictor)):
        monkeypatch.setattr(mod, "ARTIFACT_PATH", tmp_path / f"{i}.joblib")
    monkeypatch.setattr(solar_forecaster, "train", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    for mod in (price_forecaster, grid_forecaster, queue_predictor):
        monkeypatch.setattr(mod, "train", (lambda m=mod: atomic_dump({"ok": 1}, m.ARTIFACT_PATH)))
    result = scheduler.warm_models()
    assert result == {"price": True, "grid": True, "solar": None, "queue": True}
    assert scheduler.warm_models()["price"] is False, "second warm-up finds the model already there"


def test_health_endpoint_reports_scheduler_state(tmp_path):
    from fastapi.testclient import TestClient
    from main import app
    body = TestClient(app).get("/health").json()
    assert body["status"] == "ok" and body["scheduler"]["running"] in (True, False)
