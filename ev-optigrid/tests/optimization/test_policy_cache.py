"""
Policy cache robustness.

Regression for a bug found when the frontend's simulator page was first run
against the live backend: the cache wrote straight to its final filename, so a
reader arriving mid-write (or a killed process) left a truncated .npz that made
EVERY later request needing that policy crash with `BadZipFile` until the file
was deleted by hand.
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pytest

from optimization import policy as policy_module
from optimization.mdp import MDPConfig
from optimization.policy import get_or_solve_policy
from optimization.reward_model import resolve_weights


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(policy_module, "ARTIFACT_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def small_config():
    return MDPConfig(battery_capacity_kwh=60.0, max_charge_rate_kw=50.0, slot_minutes=30, horizon_slots=6)


def _solve(cfg):
    return get_or_solve_policy(cfg, resolve_weights("balanced"), target_soc_pct=90.0, minimum_safe_soc_pct=70.0)


def test_second_call_is_served_from_cache_and_identical(cache_dir, small_config):
    first, cached_first = _solve(small_config)
    second, cached_second = _solve(small_config)
    assert (cached_first, cached_second) == (False, True)
    assert np.array_equal(first.V, second.V) and np.array_equal(first.policy, second.policy)


def test_regression_truncated_cache_file_is_recovered_not_fatal(cache_dir, small_config):
    _solve(small_config)
    (cache_file,) = list(cache_dir.glob("policy_*.npz"))
    good_size = cache_file.stat().st_size
    cache_file.write_bytes(cache_file.read_bytes()[: good_size // 3])  # simulate a write killed midway
    policy_module.clear_memory_cache()                                  # a fresh process would have an empty memory cache

    policy, was_cached = _solve(small_config)          # used to raise zipfile.BadZipFile
    assert was_cached is False and policy.V.shape[0] == small_config.horizon_slots + 1
    assert _solve(small_config)[1] is True              # cache was repaired
    assert cache_file.stat().st_size == good_size


def test_garbage_cache_file_is_recovered(cache_dir, small_config):
    _solve(small_config)
    (cache_file,) = list(cache_dir.glob("policy_*.npz"))
    cache_file.write_bytes(b"this is not a zip file")
    policy_module.clear_memory_cache()
    assert _solve(small_config)[1] is False


def test_no_temp_files_left_behind(cache_dir, small_config):
    _solve(small_config)
    assert [p.name for p in cache_dir.iterdir() if ".tmp" in p.name] == []


def test_concurrent_solves_of_the_same_key_never_crash(cache_dir, small_config):
    errors, results = [], []

    def worker():
        try:
            results.append(_solve(small_config)[0])
        except Exception as e:  # noqa: BLE001 - the test is precisely "no exception"
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert errors == []
    assert len(results) == 6
    assert all(np.array_equal(results[0].policy, r.policy) for r in results)
    assert [p.name for p in cache_dir.iterdir() if ".tmp" in p.name] == []


# ── in-memory LRU layer ──────────────────────────────────────────────────
def test_memory_layer_serves_repeat_calls_without_touching_disk(cache_dir, small_config):
    first, _ = _solve(small_config)
    for f in cache_dir.glob("policy_*.npz"):
        f.unlink()                                       # disk copy gone...
    again, was_cached = _solve(small_config)
    assert was_cached is True and again is first, "...but the same in-memory object is returned"


def test_memory_cache_evicts_the_least_recently_used_entry(cache_dir, small_config, monkeypatch):
    monkeypatch.setattr(policy_module, "MEMORY_CACHE_SIZE", 2)
    cfgs = [MDPConfig(battery_capacity_kwh=c, max_charge_rate_kw=50.0, slot_minutes=30, horizon_slots=4) for c in (40.0, 50.0, 60.0)]
    _solve(cfgs[0]); _solve(cfgs[1])
    _solve(cfgs[0])                                      # touch 0 so that 1 becomes the oldest
    _solve(cfgs[2])                                      # evicts 1
    assert policy_module.memory_cache_size() == 2
    for f in cache_dir.glob("policy_*.npz"):
        f.unlink()
    assert _solve(cfgs[0])[1] is True and _solve(cfgs[2])[1] is True   # both still in memory
    assert _solve(cfgs[1])[1] is False                                  # evicted, and disk is empty -> re-solved


def test_force_resolve_bypasses_the_memory_layer(cache_dir, small_config):
    _solve(small_config)
    policy, was_cached = get_or_solve_policy(small_config, resolve_weights("balanced"), 90.0, 70.0, force_resolve=True)
    assert was_cached is False


def test_custom_transition_model_never_reuses_or_pollutes_the_cache(cache_dir, small_config):
    """The key ignores the transition model, so a custom one must not get (or leave) a default-world policy."""
    from optimization.transition_model import TransitionModel, build_default_transition_matrix
    default_policy, _ = _solve(small_config)
    sticky = TransitionModel(price_matrix=build_default_transition_matrix(3, persistence=0.99))
    custom, was_cached = get_or_solve_policy(small_config, resolve_weights("balanced"), 90.0, 70.0, transition_model=sticky)
    assert was_cached is False
    assert not np.array_equal(custom.V, default_policy.V), "different world, different value function"
    assert _solve(small_config)[0] is default_policy, "the default entry must be untouched"


def test_memory_cache_is_safe_under_concurrent_use(cache_dir, monkeypatch):
    monkeypatch.setattr(policy_module, "MEMORY_CACHE_SIZE", 3)
    errors = []
    def worker(i):
        try:
            cfg = MDPConfig(battery_capacity_kwh=40.0 + (i % 5) * 10, max_charge_rate_kw=50.0, slot_minutes=30, horizon_slots=3)
            for _ in range(3):
                _solve(cfg)
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert errors == [] and policy_module.memory_cache_size() <= 3
