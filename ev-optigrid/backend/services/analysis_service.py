"""
Analysis service: exposes the MDP/SDP internals for the academic visualisation
pages (state space, policy heatmap, Bellman breakdown, Monte Carlo, sensitivity),
the digital twin, and the battery model curves (spec §17, §32).

Nothing here re-implements the optimiser's maths: costs come from
optimization.reward_model.step_cost, the expected-future term uses the same joint
transition tensor as value iteration, and policies come from the same cache.
The Bellman breakdown then CHECKS its own arithmetic against the solver's value
function, so the page demonstrates the equation rather than merely asserting it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for optimization/

import numpy as np

from optimization.battery_model import (
    BatteryDegradationWeights, battery_health_indicator, compute_degradation_cost,
    depth_of_discharge_term, high_charging_power_term, high_soc_exposure_term, temperature_term,
)
from optimization.mdp import (
    DEFAULT_ACTIONS_KW, DEFAULT_GRID_LOAD_THRESHOLDS, DEFAULT_PRICE_THRESHOLDS, DEFAULT_SOLAR_THRESHOLDS,
    GRID_LEVELS, N_GRID, N_PRICE, N_SOC, N_SOLAR, PRICE_LEVELS, SOC_BUCKETS, SOC_STEP, SOLAR_LEVELS, MDPConfig,
    bucketize_grid_load, bucketize_price, bucketize_solar, nearest_soc_bucket_index, soc_from_bucket_index,
    soc_transition_distribution,
)
from optimization.policy import get_or_solve_policy
from optimization.reward_model import (
    DEFAULT_GRID_LOAD_VALUES, DEFAULT_PRICE_VALUES, DEFAULT_SOLAR_AVAIL_VALUES, ProfileWeights,
    real_electricity_cost, resolve_weights, step_cost,
)
from optimization.transition_model import TransitionModel
from optimization.value_iteration import _joint_transition_tensor

GAMMA = 0.99   # solve_value_iteration's default discount factor
PROFILES = ("balanced", "save_money", "fastest", "battery_health", "green")
_TM = TransitionModel()          # the same default Markov chains the solver uses
MAX_MONTE_CARLO_WORK = 60_000    # n_runs * horizon_slots


# ── helpers ───────────────────────────────────────────────────────────────
def _config(p) -> MDPConfig:
    return MDPConfig(battery_capacity_kwh=p.battery_capacity_kwh, max_charge_rate_kw=p.max_charge_rate_kw,
                     slot_minutes=p.slot_minutes, horizon_slots=p.horizon_slots)


def _solve(p, weights: ProfileWeights | None = None):
    return get_or_solve_policy(_config(p), weights or resolve_weights(p.profile),
                               p.target_soc_pct, p.minimum_safe_soc_pct)


def _start_state(c) -> tuple[int, int, int]:
    return (bucketize_price(c.current_price_per_kwh), bucketize_grid_load(c.current_grid_load_pct),
            bucketize_solar(c.current_solar_availability_frac))


def _matrix(m: np.ndarray) -> list[list[float]]:
    return [[round(float(x), 6) for x in row] for row in m]


# ── 1. state space & SOC transition ───────────────────────────────────────
def state_space() -> dict:
    exogenous = N_PRICE * N_GRID * N_SOLAR
    return {
        "soc_buckets": [float(x) for x in SOC_BUCKETS], "soc_step_pct": SOC_STEP,
        "price": {"levels": list(PRICE_LEVELS), "values_inr_per_kwh": [DEFAULT_PRICE_VALUES[i] for i in range(N_PRICE)],
                  "thresholds": list(DEFAULT_PRICE_THRESHOLDS)},
        "grid": {"levels": list(GRID_LEVELS), "values_load_pct": [DEFAULT_GRID_LOAD_VALUES[i] for i in range(N_GRID)],
                 "thresholds": list(DEFAULT_GRID_LOAD_THRESHOLDS)},
        "solar": {"levels": list(SOLAR_LEVELS), "values_fraction": [DEFAULT_SOLAR_AVAIL_VALUES[i] for i in range(N_SOLAR)],
                  "thresholds": list(DEFAULT_SOLAR_THRESHOLDS)},
        "actions_kw": list(DEFAULT_ACTIONS_KW),
        "counts": {"soc": N_SOC, "price": N_PRICE, "grid": N_GRID, "solar": N_SOLAR, "exogenous_states": exogenous,
                   "states_per_slot": N_SOC * exogenous, "actions": len(DEFAULT_ACTIONS_KW),
                   "state_action_pairs_per_slot": N_SOC * exogenous * len(DEFAULT_ACTIONS_KW)},
        "transition_matrices": {"price": _matrix(_TM.price_matrix), "grid": _matrix(_TM.grid_matrix),
                                "solar": _matrix(_TM.solar_matrix)},
        "gamma": GAMMA,
        "notes": ["Price, grid load and solar are modelled as independent Markov chains given their current level.",
                  "SOC is discretised in 5-point buckets; SOC transitions are linearly interpolated between buckets."],
    }


def soc_transition(soc_pct: float, action_kw: float, battery_capacity_kwh: float, slot_minutes: int,
                   charging_efficiency: float = 0.90) -> dict:
    cfg = MDPConfig(battery_capacity_kwh=battery_capacity_kwh, max_charge_rate_kw=max(action_kw, 1.0),
                    slot_minutes=slot_minutes, charging_efficiency=charging_efficiency)
    gain = cfg.soc_gain_pct(action_kw)
    after = max(0.0, min(100.0, soc_pct + gain))
    dist = soc_transition_distribution(soc_pct, gain)
    return {
        "soc_before_pct": soc_pct, "gain_pct": round(gain, 4), "soc_after_continuous_pct": round(after, 4),
        "distribution": [{"probability": round(pr, 6), "bucket_index": b, "bucket_soc_pct": float(SOC_BUCKETS[b])}
                         for pr, b in dist],
        "expected_bucket_soc_pct": round(sum(pr * float(SOC_BUCKETS[b]) for pr, b in dist), 4),
        "nearest_bucket_soc_pct": float(SOC_BUCKETS[nearest_soc_bucket_index(after)]),
        "start_bucket_soc_pct": float(SOC_BUCKETS[nearest_soc_bucket_index(soc_pct)]),
    }


# ── 2. policy heatmap ─────────────────────────────────────────────────────
def policy_heatmap(req) -> dict:
    policy, cached = _solve(req)
    acts, T = policy.actions_kw, req.horizon_slots
    pl, gl, sl = req.price_level, req.grid_level, req.solar_level

    if req.mode == "soc_by_time":
        x_label, x_values = "Time slot", list(range(T))
        action = [[float(acts[int(policy.policy[t, i, pl, gl, sl])]) for t in range(T)] for i in range(N_SOC)]
        value = [[float(policy.V[t, i, pl, gl, sl]) for t in range(T)] for i in range(N_SOC)]
    else:
        if req.t >= T:
            raise ValueError(f"t must be below horizon_slots ({T})")
        names = {"price": PRICE_LEVELS, "grid": GRID_LEVELS, "solar": SOLAR_LEVELS}[req.vary]
        x_label, x_values = f"{req.vary} level", list(names)
        def idx(level_j):
            return {"price": (level_j, gl, sl), "grid": (pl, level_j, sl), "solar": (pl, gl, level_j)}[req.vary]
        action = [[float(acts[int(policy.policy[(req.t, i, *idx(j))])]) for j in range(len(names))] for i in range(N_SOC)]
        value = [[float(policy.V[(req.t, i, *idx(j))]) for j in range(len(names))] for i in range(N_SOC)]

    return {"mode": req.mode, "x_label": x_label, "x_values": x_values, "y_label": "State of charge (%)",
            "y_values": [float(s) for s in SOC_BUCKETS], "action_kw": action, "value": value,
            "max_action_kw": float(max(acts)), "cached": cached,
            "fixed": {"price_level": PRICE_LEVELS[pl], "grid_level": GRID_LEVELS[gl], "solar_level": SOLAR_LEVELS[sl],
                      "t": req.t if req.mode == "soc_by_level" else None}}


# ── 3. Bellman breakdown ──────────────────────────────────────────────────
def _only(weights: ProfileWeights, keep: str) -> ProfileWeights:
    return ProfileWeights(**{k: (v if k == keep else 0.0) for k, v in weights.__dict__.items()})


def bellman(req) -> dict:
    T = req.horizon_slots
    if req.t >= T:
        raise ValueError(f"t must be below horizon_slots ({T})")
    policy, cached = _solve(req)
    cfg, weights = policy.config, resolve_weights(req.profile)
    soc_idx = nearest_soc_bucket_index(req.soc_pct)
    soc = soc_from_bucket_index(soc_idx)
    p, g, s = req.price_level, req.grid_level, req.solar_level
    joint = _joint_transition_tensor(_TM)
    V_next = policy.V[req.t + 1]

    terms = {"electricity": "w_cost", "degradation": "w_battery", "grid": "w_grid", "renewable": "w_renewable"}
    rows = []
    for a_kw in policy.actions_kw:
        gain = cfg.soc_gain_pct(a_kw)
        soc_after = max(0.0, min(100.0, soc + gain))
        dist = soc_transition_distribution(soc, gain)
        actual_gain = soc_after - soc
        eff_kw = 0.0
        if cfg.slot_hours > 0 and cfg.charging_efficiency > 0:
            eff_kw = ((actual_gain / 100.0) * cfg.battery_capacity_kwh) / (cfg.charging_efficiency * cfg.slot_hours)
        eff_kw = max(0.0, min(a_kw, eff_kw))

        def cost(w):
            return step_cost(soc_before_pct=soc, soc_after_pct=soc_after, action_kw=eff_kw,
                             max_charge_rate_kw=cfg.max_charge_rate_kw, price_idx=p, grid_idx=g, solar_idx=s,
                             slot_hours=cfg.slot_hours, weights=w)

        total = cost(weights)
        comps = {name: cost(_only(weights, field)) for name, field in terms.items()}
        expected_future = sum(pr * float(np.einsum("ijk,ijk->", joint[p, g, s], V_next[b])) for pr, b in dist)
        q = total + GAMMA * expected_future
        rows.append({"action_kw": float(a_kw), "soc_after_pct": round(soc_after, 3), "delivered_kw": round(eff_kw, 3),
                     "immediate_cost": {**{k: round(v, 6) for k, v in comps.items()}, "total": round(total, 6)},
                     "components_add_up": bool(abs(sum(comps.values()) - total) < 1e-9),
                     "expected_future_value": round(expected_future, 6),
                     "discounted_future_value": round(GAMMA * expected_future, 6), "q_value": round(q, 6),
                     "real_cost_inr": round(real_electricity_cost(eff_kw, p, cfg.slot_hours), 4),
                     "next_soc_distribution": [{"probability": round(pr, 4), "soc_pct": float(SOC_BUCKETS[b])} for pr, b in dist]})

    best = None
    for i, r in enumerate(rows):                       # same tie-break as the solver: first strictly-lowest wins
        if best is None or r["q_value"] < rows[best]["q_value"]:
            best = i
    for i, r in enumerate(rows):
        r["is_best"] = i == best
    v_solver = float(policy.V[req.t, soc_idx, p, g, s])
    policy_action = float(policy.actions_kw[int(policy.policy[req.t, soc_idx, p, g, s])])
    q_of_policy = next(r["q_value"] for r in rows if r["action_kw"] == policy_action)
    return {"t": req.t, "state": {"soc_pct": soc, "price_level": PRICE_LEVELS[p], "grid_level": GRID_LEVELS[g],
                                   "solar_level": SOLAR_LEVELS[s]},
            "gamma": GAMMA, "next_is_terminal": req.t == T - 1, "actions": rows,
            "best_action_kw": rows[best]["action_kw"], "min_q": rows[best]["q_value"],
            "solver_value_function": round(v_solver, 6), "residual": abs(rows[best]["q_value"] - v_solver),
            "solver_policy_action_kw": policy_action,
            "matches_solver": bool(q_of_policy <= rows[best]["q_value"] + 1e-9 and abs(rows[best]["q_value"] - v_solver) < 1e-6),
            "cached": cached}


# ── rollouts (Monte Carlo + digital twin) ─────────────────────────────────
def _sample_paths(rng: np.random.Generator, n: int, T: int, start: tuple[int, int, int]) -> np.ndarray:
    """(n, T, 3) integer array of (price, grid, solar) levels per slot; slot 0 is the observed state."""
    cums = [np.cumsum(m, axis=1) for m in (_TM.price_matrix, _TM.grid_matrix, _TM.solar_matrix)]
    u = rng.random((n, T, 3))
    paths = np.empty((n, T, 3), dtype=int)
    paths[:, 0, :] = start
    for t in range(1, T):
        for k, cum in enumerate(cums):
            paths[:, t, k] = np.minimum((cum[paths[:, t - 1, k]] < u[:, t, k][:, None]).sum(axis=1), cum.shape[0] - 1)
    return paths


def _policy_fns(policy, target_soc_pct: float) -> dict:
    max_kw = float(max(policy.actions_kw))
    return {
        "sdp": lambda t, soc, p, g, s: float(policy.action_kw(t, soc, p, g, s)),
        "charge_immediately": lambda t, soc, p, g, s: max_kw if soc < target_soc_pct else 0.0,
        "off_peak_only": lambda t, soc, p, g, s: max_kw if (p == 0 and soc < target_soc_pct) else 0.0,
    }


def _rollout(fn, cfg: MDPConfig, init_soc: float, path, record: bool = False) -> dict:
    soc, cost, deg, energy, grid_kw_weighted = init_soc, 0.0, 0.0, 0.0, 0.0
    cap, eff, sh = cfg.battery_capacity_kwh, cfg.charging_efficiency, cfg.slot_hours
    recs = []
    for t in range(len(path)):
        p, g, s = int(path[t][0]), int(path[t][1]), int(path[t][2])
        a = fn(t, soc, p, g, s)
        soc_after = min(100.0, soc + cfg.soc_gain_pct(a))
        eff_kw = min(a, ((soc_after - soc) / 100.0 * cap) / (eff * sh)) if a > 0 else 0.0
        slot_cost = real_electricity_cost(eff_kw, p, sh)
        wear = compute_degradation_cost(soc, soc_after, eff_kw, cfg.max_charge_rate_kw) if eff_kw > 0 else 0.0
        cost += slot_cost
        deg += wear
        energy += eff_kw * sh
        grid_kw_weighted += eff_kw * DEFAULT_GRID_LOAD_VALUES[g]
        if record:
            recs.append({"t": t, "clock_min": t * cfg.slot_minutes, "soc_before_pct": round(soc, 3),
                         "soc_after_pct": round(soc_after, 3), "action_kw": round(a, 3), "delivered_kw": round(eff_kw, 3),
                         "price_level": PRICE_LEVELS[p], "price_inr_per_kwh": DEFAULT_PRICE_VALUES[p],
                         "grid_level": GRID_LEVELS[g], "grid_load_pct": DEFAULT_GRID_LOAD_VALUES[g],
                         "solar_level": SOLAR_LEVELS[s], "solar_fraction": DEFAULT_SOLAR_AVAIL_VALUES[s],
                         "slot_cost_inr": round(slot_cost, 4), "cumulative_cost_inr": round(cost, 4),
                         "cumulative_energy_kwh": round(energy, 4), "degradation": round(wear, 5)})
        soc = soc_after
    out = {"cost_inr": cost, "final_soc_pct": soc, "degradation": deg, "energy_kwh": energy,
           "grid_load_when_charging_pct": (grid_kw_weighted / (energy / sh) if energy > 0 else None)}
    if record:
        out["records"] = recs
    return out


def _summ(values) -> dict:
    a = np.asarray(values, dtype=float)
    return {"mean": float(a.mean()), "std": float(a.std()), "p05": float(np.percentile(a, 5)),
            "p50": float(np.percentile(a, 50)), "p95": float(np.percentile(a, 95)),
            "min": float(a.min()), "max": float(a.max())}


def _histogram(series: dict[str, list[float]], bins: int = 12) -> dict:
    lo = min(min(v) for v in series.values())
    hi = max(max(v) for v in series.values())
    if hi - lo < 1e-9:
        hi = lo + 1.0
    edges = np.linspace(lo, hi, bins + 1)
    return {"edges": [round(float(e), 4) for e in edges],
            "counts": {k: [int(c) for c in np.histogram(v, bins=edges)[0]] for k, v in series.items()}}


# ── 4. Monte Carlo ────────────────────────────────────────────────────────
def monte_carlo(req) -> dict:
    if req.n_runs * req.horizon_slots > MAX_MONTE_CARLO_WORK:
        raise ValueError(f"n_runs x horizon_slots = {req.n_runs * req.horizon_slots:,} exceeds the limit of "
                         f"{MAX_MONTE_CARLO_WORK:,}. Reduce the runs or the horizon.")
    policy, _ = _solve(req)
    cfg = policy.config
    fns = _policy_fns(policy, req.target_soc_pct)
    rng = np.random.default_rng(req.seed)
    paths = _sample_paths(rng, req.n_runs, req.horizon_slots, _start_state(req))

    results = {name: [_rollout(fn, cfg, req.current_soc_pct, path) for path in paths] for name, fn in fns.items()}
    policies = {}
    for name, runs in results.items():
        loads = [r["grid_load_when_charging_pct"] for r in runs if r["grid_load_when_charging_pct"] is not None]
        policies[name] = {
            "cost_inr": _summ([r["cost_inr"] for r in runs]),
            "final_soc_pct": _summ([r["final_soc_pct"] for r in runs]),
            "degradation": _summ([r["degradation"] for r in runs]),
            "energy_kwh": _summ([r["energy_kwh"] for r in runs]),
            "target_met_pct": 100.0 * float(np.mean([r["final_soc_pct"] >= req.target_soc_pct - 1e-9 for r in runs])),
            "safe_soc_met_pct": 100.0 * float(np.mean([r["final_soc_pct"] >= req.minimum_safe_soc_pct - 1e-9 for r in runs])),
            "grid_load_when_charging_pct": float(np.mean(loads)) if loads else None,
        }

    def paired(other: str) -> dict:
        diff = np.array([o["cost_inr"] - s["cost_inr"] for o, s in zip(results[other], results["sdp"])])
        half = 1.96 * diff.std(ddof=1) / np.sqrt(len(diff)) if len(diff) > 1 else 0.0
        return {"mean_saving_inr": float(diff.mean()), "ci95_low": float(diff.mean() - half),
                "ci95_high": float(diff.mean() + half), "sdp_cheaper_pct": 100.0 * float(np.mean(diff > 1e-9)),
                "sdp_cheaper_or_equal_pct": 100.0 * float(np.mean(diff >= -1e-9))}

    return {"n_runs": req.n_runs, "seed": req.seed,
            "start": dict(zip(("price_level", "grid_level", "solar_level"),
                              (PRICE_LEVELS[_start_state(req)[0]], GRID_LEVELS[_start_state(req)[1]], SOLAR_LEVELS[_start_state(req)[2]]))),
            "policies": policies,
            "histograms": {"cost_inr": _histogram({k: [r["cost_inr"] for r in v] for k, v in results.items()}),
                           "final_soc_pct": _histogram({k: [r["final_soc_pct"] for r in v] for k, v in results.items()})},
            "paired_vs": {"charge_immediately": paired("charge_immediately"), "off_peak_only": paired("off_peak_only")},
            "note": "All policies are evaluated on the SAME simulated price/grid/solar paths, so differences are paired. "
                    "Costs are real rupees at the charger (before charging losses)."}


# ── 5. sensitivity ────────────────────────────────────────────────────────
def sensitivity(req) -> dict:
    p0, g0, s0 = _start_state(req)
    points: list[dict] = []
    if req.sweep in ("soc", "price", "grid", "solar"):
        policy, _ = _solve(req)
        grids = {"soc": [float(x) for x in np.arange(0, 101, 5)], "price": [float(x) for x in np.arange(2, 17, 1)],
                 "grid": [float(x) for x in np.arange(20, 101, 5)], "solar": [round(float(x), 2) for x in np.arange(0, 1.01, 0.1)]}
        for x in grids[req.sweep]:
            soc, p, g, s = req.current_soc_pct, p0, g0, s0
            if req.sweep == "soc": soc = x
            elif req.sweep == "price": p = bucketize_price(x)
            elif req.sweep == "grid": g = bucketize_grid_load(x)
            else: s = bucketize_solar(x)
            level = {"soc": "", "price": PRICE_LEVELS[p], "grid": GRID_LEVELS[g], "solar": SOLAR_LEVELS[s]}[req.sweep]
            points.append({"x": x, "label": str(x), "level": level, "action_kw": float(policy.action_kw(0, soc, p, g, s)),
                           "value": policy.value_at(0, soc, p, g, s)})
        unit = {"soc": "State of charge (%)", "price": "Electricity price (₹/kWh)",
                "grid": "Grid load (%)", "solar": "Solar availability (fraction)"}[req.sweep]
    elif req.sweep == "profile":
        for name in PROFILES:
            policy, _ = _solve(req.model_copy(update={"profile": name}))
            points.append({"x": name, "label": name, "level": "", "action_kw": float(policy.action_kw(0, req.current_soc_pct, p0, g0, s0)),
                           "value": policy.value_at(0, req.current_soc_pct, p0, g0, s0)})
        unit = "Optimisation profile"
    else:  # cost_weight: scale the electricity-cost weight of the chosen profile
        base = resolve_weights(req.profile)
        for m in (0.25, 0.5, 1.0, 2.0, 4.0):
            w = ProfileWeights(**{**base.__dict__, "w_cost": base.w_cost * m})
            policy, _ = _solve(req, weights=w)
            points.append({"x": m, "label": f"x{m:g}", "level": "", "action_kw": float(policy.action_kw(0, req.current_soc_pct, p0, g0, s0)),
                           "value": policy.value_at(0, req.current_soc_pct, p0, g0, s0)})
        unit = "Electricity-cost weight multiplier"
    return {"sweep": req.sweep, "x_label": unit, "points": points,
            "held_fixed": {"soc_pct": req.current_soc_pct, "price_level": PRICE_LEVELS[p0], "grid_level": GRID_LEVELS[g0],
                           "solar_level": SOLAR_LEVELS[s0], "profile": req.profile},
            "note": "Action is the recommendation for the FIRST time slot. Price, grid and solar are bucketed into "
                    "three levels, so their curves are step functions by design."}


# ── 6. digital twin ───────────────────────────────────────────────────────
def twin_run(req) -> dict:
    policy, _ = _solve(req)
    cfg = policy.config
    fns = _policy_fns(policy, req.target_soc_pct)
    path = _sample_paths(np.random.default_rng(req.seed), 1, req.horizon_slots, _start_state(req))[0]
    lanes = {name: _rollout(fns[name], cfg, req.current_soc_pct, path, record=True) for name in ("sdp", "charge_immediately")}
    return {"config": {"battery_capacity_kwh": cfg.battery_capacity_kwh, "max_charge_rate_kw": cfg.max_charge_rate_kw,
                       "slot_minutes": cfg.slot_minutes, "horizon_slots": cfg.horizon_slots,
                       "target_soc_pct": req.target_soc_pct, "minimum_safe_soc_pct": req.minimum_safe_soc_pct,
                       "start_soc_pct": req.current_soc_pct, "profile": req.profile, "seed": req.seed},
            "lanes": lanes,
            "note": "Both lanes face the identical simulated price, grid-load and solar path (a stochastic scenario, not live data)."}


# ── 7. battery model curves ───────────────────────────────────────────────
def battery_curves(max_charge_rate_kw: float, ambient_temp_c: float | None) -> dict:
    w = BatteryDegradationWeights()

    def parts(soc_before, soc_after, kw, temp):
        c = {"depth_of_discharge": w.k_dod * depth_of_discharge_term(soc_before, soc_after),
             "high_soc_exposure": w.k_high_soc * high_soc_exposure_term(soc_after),
             "charge_rate": w.k_charge_rate * high_charging_power_term(kw, max_charge_rate_kw),
             "temperature": w.k_temperature * temperature_term(temp)}
        total = compute_degradation_cost(soc_before, soc_after, kw, max_charge_rate_kw, temp)
        return {"components": {k: round(v, 5) for k, v in c.items()}, "total": round(total, 5)}

    temp = ambient_temp_c
    by_power = [{"x": round(f * 100), **parts(30.0, 80.0, f * max_charge_rate_kw, temp)} for f in np.arange(0.1, 1.001, 0.05)]
    by_end_soc = [{"x": float(e), **parts(30.0, float(e), 0.5 * max_charge_rate_kw, temp)} for e in range(40, 101, 5)]
    by_temp = [{"x": float(t), **parts(30.0, 80.0, 0.5 * max_charge_rate_kw, float(t))} for t in range(-10, 51, 5)]
    health = [{"x": float(c), "health_pct": round(battery_health_indicator(float(c)), 2)} for c in range(0, 1001, 50)]
    return {"weights": w.__dict__, "max_charge_rate_kw": max_charge_rate_kw, "ambient_temp_c": temp,
            "by_charge_power": {"x_label": "Charging power (% of max)", "window": "30% to 80%", "points": by_power},
            "by_end_soc": {"x_label": "Charge to (%)", "window": "from 30% at half power", "points": by_end_soc},
            "by_temperature": {"x_label": "Ambient temperature (°C)", "window": "30% to 80% at half power", "points": by_temp},
            "health_indicator": {"x_label": "Cumulative wear (unitless)", "points": health},
            "note": "Illustrative model with hand-set weights; not calibrated against real degradation data."}
