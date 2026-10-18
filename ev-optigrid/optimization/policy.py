"""
Policy persistence (spec §36: "Do not run full SDP training on every
request. Cache learned policies.").

A solved policy depends on: (battery_capacity, max_charge_rate, slot config,
horizon, profile weights, target/minimum SOC). We hash those into a cache
key and persist the solved arrays to disk under optimization/artifacts/, so
identical requests reuse a previous solve. A real deployment would key this
by region + profile and refresh it on a schedule as forecasts update; this
module gives the mechanism, `services/optimization_service.py` (Phase 12)
supplies the refresh policy.
"""
import hashlib
import json
import os
import threading
import uuid
import zipfile
from collections import OrderedDict
from pathlib import Path

import numpy as np

from optimization.mdp import MDPConfig
from optimization.reward_model import ProfileWeights
from optimization.transition_model import TransitionModel
from optimization.value_iteration import SolvedPolicy, solve_value_iteration

ARTIFACT_DIR = Path(__file__).parent / "artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)


def _cache_key(config: MDPConfig, weights: ProfileWeights, target_soc: float, min_safe_soc: float) -> str:
    payload = {
        "battery_capacity_kwh": round(config.battery_capacity_kwh, 3),
        "max_charge_rate_kw": round(config.max_charge_rate_kw, 3),
        "charging_efficiency": round(config.charging_efficiency, 3),
        "slot_minutes": config.slot_minutes,
        "horizon_slots": config.horizon_slots,
        "actions_kw": config.actions_kw,
        "weights": weights.__dict__,
        "target_soc": round(target_soc, 2),
        "min_safe_soc": round(min_safe_soc, 2),
    }
    raw = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:24]


# ── in-memory LRU in front of the disk cache (synopsis stack: "Redis / In-memory LRU") ──────────────
# Reading and decompressing an .npz for every request is wasted work when the same few policies are
# asked for repeatedly (the analysis pages do exactly that). Keys include ARTIFACT_DIR, so tests that
# point the cache at a temp folder stay isolated from each other.
MEMORY_CACHE_SIZE = int(os.getenv("POLICY_MEMORY_CACHE_SIZE", "128"))
_memory: "OrderedDict[str, SolvedPolicy]" = OrderedDict()
_memory_lock = threading.Lock()


def clear_memory_cache() -> None:
    with _memory_lock:
        _memory.clear()


def memory_cache_size() -> int:
    with _memory_lock:
        return len(_memory)


def _memory_get(mkey: str):
    with _memory_lock:
        policy = _memory.get(mkey)
        if policy is not None:
            _memory.move_to_end(mkey)          # most recently used goes to the back
        return policy


def _memory_put(mkey: str, policy: SolvedPolicy) -> None:
    with _memory_lock:
        _memory[mkey] = policy
        _memory.move_to_end(mkey)
        while len(_memory) > max(1, MEMORY_CACHE_SIZE):
            _memory.popitem(last=False)         # evict the least recently used


def get_or_solve_policy(
    config: MDPConfig,
    weights: ProfileWeights,
    target_soc_pct: float,
    minimum_safe_soc_pct: float,
    transition_model: TransitionModel | None = None,
    force_resolve: bool = False,
) -> tuple[SolvedPolicy, bool]:
    """Returns (policy, was_cached). Lookup order: memory LRU, then disk, then solve.

    The cache key does not include the transition model, so a CUSTOM `transition_model` bypasses both
    caches entirely (otherwise it would silently get a policy solved for the default one).
    """
    key = _cache_key(config, weights, target_soc_pct, minimum_safe_soc_pct)
    path = ARTIFACT_DIR / f"policy_{key}.npz"
    mkey = f"{ARTIFACT_DIR}::{key}"
    use_cache = transition_model is None and not force_resolve

    if use_cache:
        hit = _memory_get(mkey)
        if hit is not None:
            return hit, True
        if path.exists():
            cached = _load_cached(path, config, target_soc_pct, minimum_safe_soc_pct)
            if cached is not None:
                _memory_put(mkey, cached)
                return cached, True
            # Unreadable/truncated cache file: fall through and re-solve (it is rewritten below).

    policy = solve_value_iteration(
        config=config, weights=weights,
        target_soc_pct=target_soc_pct, minimum_safe_soc_pct=minimum_safe_soc_pct,
        transition_model=transition_model,
    )
    if transition_model is None:            # never persist a policy solved for a non-default world
        _save_atomically(path, policy)
        _memory_put(mkey, policy)
    return policy, False


def _load_cached(path: Path, config: MDPConfig, target_soc_pct: float, minimum_safe_soc_pct: float):
    """Returns the cached policy, or None (and removes the file) if it can't be read.

    A cache file can be unreadable if a previous process was killed mid-write
    (older versions wrote straight to the final path) or the disk was full.
    A bad cache must cost a re-solve, never a crash on every later request.
    """
    try:
        # allow_pickle=False: the arrays are plain numeric data, and unpickling
        # files from a cache directory is an unnecessary risk.
        with np.load(path, allow_pickle=False) as data:
            return SolvedPolicy(
                V=data["V"], policy=data["policy"], actions_kw=tuple(data["actions_kw"]),
                config=config, target_soc_pct=target_soc_pct, minimum_safe_soc_pct=minimum_safe_soc_pct,
            )
    except (zipfile.BadZipFile, OSError, ValueError, KeyError, EOFError):
        path.unlink(missing_ok=True)
        return None


def _save_atomically(path: Path, policy: SolvedPolicy) -> None:
    """Write to a unique temp file, then rename into place.

    os.replace is atomic on the same filesystem, so a concurrent reader sees
    either no file or a complete one, never a half-written one. The temp name
    is unique per call so two workers solving the same key can't clobber each other.
    """
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp.npz")
    try:
        np.savez_compressed(tmp, V=policy.V, policy=policy.policy, actions_kw=np.array(policy.actions_kw))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)  # only exists if the write or rename failed
