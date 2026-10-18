"""
Tests for the analysis / digital-twin / fleet / battery endpoints.

These assert properties of the underlying maths (not just response shapes):
the Bellman breakdown must reproduce the solver's own value function and action;
SOC interpolation must be unbiased; the twin's two lanes must see the same world;
the fleet allocator must never break a physical constraint.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pytest

from tests.backend.test_api_endpoints import anonymous_client, client  # noqa: F401  (shared fixtures)


@pytest.fixture(autouse=True)
def _isolated_policy_cache(tmp_path, monkeypatch):
    from optimization import policy
    monkeypatch.setattr(policy, "ARTIFACT_DIR", tmp_path / "policies")
    (tmp_path / "policies").mkdir()


# ── authentication ────────────────────────────────────────────────────────
NEW_PROTECTED = [
    ("get", "/api/analysis/state-space", None),
    ("get", "/api/analysis/soc-transition", None),
    ("post", "/api/analysis/policy-heatmap", {}),
    ("post", "/api/analysis/bellman", {}),
    ("post", "/api/analysis/monte-carlo", {}),
    ("post", "/api/analysis/sensitivity", {}),
    ("post", "/api/twin/run", {}),
    ("post", "/api/fleet/allocate", {"vehicles": [], "chargers": [], "grid_capacity_kw": 1}),
    ("get", "/api/battery/curves", None),
]


@pytest.mark.parametrize("method,path,body", NEW_PROTECTED)
def test_new_endpoints_require_login(anonymous_client, method, path, body):  # noqa: F811
    r = getattr(anonymous_client, method)(path, **({"json": body} if body is not None else {}))
    assert r.status_code == 401


# ── state space & SOC transition ──────────────────────────────────────────
def test_state_space_counts_and_stochastic_matrices(client):  # noqa: F811
    body = client.get("/api/analysis/state-space").json()
    c = body["counts"]
    assert c["states_per_slot"] == c["soc"] * c["exogenous_states"] == 21 * 27
    assert c["state_action_pairs_per_slot"] == c["states_per_slot"] * c["actions"]
    for name, m in body["transition_matrices"].items():
        assert all(abs(sum(row) - 1.0) < 1e-4 for row in m), f"{name} rows must sum to 1"


@pytest.mark.parametrize("soc,kw,cap", [(30, 5, 60), (30, 5, 100), (47, 7.5, 40.5), (83, 20, 60), (0, 50, 60)])
def test_soc_interpolation_is_unbiased(client, soc, kw, cap):  # noqa: F811
    """The property that fixed the 'slow charger gets zero charge' bug (docs/MDP.md §12):
    the EXPECTED next bucket must equal the true continuous SOC, so small gains accumulate."""
    r = client.get("/api/analysis/soc-transition",
                   params={"soc_pct": soc, "action_kw": kw, "battery_capacity_kwh": cap}).json()
    assert abs(sum(d["probability"] for d in r["distribution"]) - 1.0) < 1e-6
    assert abs(r["expected_bucket_soc_pct"] - r["soc_after_continuous_pct"]) < 1e-2


# ── policy heatmap ────────────────────────────────────────────────────────
def test_heatmap_shape_and_valid_actions(client):  # noqa: F811
    h = client.post("/api/analysis/policy-heatmap", json={}).json()
    assert len(h["action_kw"]) == 21 and all(len(row) == 24 for row in h["action_kw"])
    allowed = {0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0}
    assert {a for row in h["action_kw"] for a in row} <= allowed


def test_full_battery_never_charges_in_the_heatmap(client):  # noqa: F811
    h = client.post("/api/analysis/policy-heatmap", json={"price_level": 0, "grid_level": 0, "solar_level": 2}).json()
    assert h["y_values"][-1] == 100.0 and set(h["action_kw"][-1]) == {0.0}


def test_heatmap_by_level_and_validation(client):  # noqa: F811
    h = client.post("/api/analysis/policy-heatmap", json={"mode": "soc_by_level", "vary": "grid", "t": 3}).json()
    assert h["x_values"] == ["low", "medium", "high"] and len(h["action_kw"][0]) == 3
    assert client.post("/api/analysis/policy-heatmap", json={"mode": "soc_by_level", "t": 24}).status_code == 422
    assert client.post("/api/analysis/policy-heatmap", json={"minimum_safe_soc_pct": 95, "target_soc_pct": 80}).status_code == 422
    assert client.post("/api/analysis/policy-heatmap", json={"price_level": 3}).status_code == 422


# ── Bellman breakdown ─────────────────────────────────────────────────────
@pytest.mark.parametrize("t,soc,price,grid,solar", [
    (0, 30, 0, 1, 2), (0, 30, 2, 2, 0), (5, 10, 1, 1, 1), (12, 55, 0, 2, 0), (23, 80, 1, 0, 1), (0, 100, 1, 1, 1), (23, 0, 2, 2, 2)])
def test_bellman_breakdown_reproduces_the_solvers_value_and_action(client, t, soc, price, grid, solar):  # noqa: F811
    b = client.post("/api/analysis/bellman", json={"t": t, "soc_pct": soc, "price_level": price,
                                                    "grid_level": grid, "solar_level": solar}).json()
    assert b["matches_solver"] is True, f"residual {b['residual']}"
    assert b["residual"] < 1e-5
    assert all(a["components_add_up"] for a in b["actions"])
    best = min(b["actions"], key=lambda a: a["q_value"])
    assert b["actions"][[a["is_best"] for a in b["actions"]].index(True)]["q_value"] == pytest.approx(best["q_value"])
    # Bellman: Q = immediate cost + gamma * E[V_next]
    for a in b["actions"]:
        assert a["q_value"] == pytest.approx(a["immediate_cost"]["total"] + a["discounted_future_value"], abs=1e-5)
    assert b["next_is_terminal"] is (t == 23)


def test_bellman_validation(client):  # noqa: F811
    assert client.post("/api/analysis/bellman", json={"t": 24}).status_code == 422


# ── Monte Carlo ───────────────────────────────────────────────────────────
def test_monte_carlo_is_reproducible_and_histograms_are_complete(client):  # noqa: F811
    body = {"n_runs": 200, "horizon_slots": 8, "seed": 5}
    a = client.post("/api/analysis/monte-carlo", json=body).json()
    b = client.post("/api/analysis/monte-carlo", json=body).json()
    assert a == b, "same seed must give identical results"
    assert client.post("/api/analysis/monte-carlo", json={**body, "seed": 6}).json() != a
    for hist in a["histograms"].values():
        for name, counts in hist["counts"].items():
            assert sum(counts) == 200, f"{name} histogram must account for every run"
    assert set(a["policies"]) == {"sdp", "charge_immediately", "off_peak_only"}


def test_monte_carlo_charge_immediately_reaches_target_and_costs_more(client):  # noqa: F811
    r = client.post("/api/analysis/monte-carlo", json={"n_runs": 300, "horizon_slots": 8}).json()
    fast = r["policies"]["charge_immediately"]
    assert fast["target_met_pct"] == 100.0
    assert r["policies"]["sdp"]["cost_inr"]["mean"] < fast["cost_inr"]["mean"]
    paired = r["paired_vs"]["charge_immediately"]
    assert paired["ci95_low"] <= paired["mean_saving_inr"] <= paired["ci95_high"]
    assert paired["mean_saving_inr"] > 0


def test_monte_carlo_work_limit(client):  # noqa: F811
    r = client.post("/api/analysis/monte-carlo", json={"n_runs": 2000, "horizon_slots": 96})
    assert r.status_code == 422 and "limit" in r.json()["detail"]


# ── sensitivity ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("sweep", ["soc", "price", "grid", "solar", "profile", "cost_weight"])
def test_every_sensitivity_sweep_returns_points(client, sweep):  # noqa: F811
    r = client.post("/api/analysis/sensitivity", json={"sweep": sweep, "horizon_slots": 8, "current_soc_pct": 40}).json()
    assert len(r["points"]) >= 5 and all("action_kw" in p and "value" in p for p in r["points"])


def test_sensitivity_behaves_economically_at_a_short_horizon(client):  # noqa: F811
    """More expensive electricity or a more stressed grid must never make the optimiser charge HARDER."""
    for sweep in ("price", "grid"):
        pts = client.post("/api/analysis/sensitivity", json={"sweep": sweep, "horizon_slots": 8, "current_soc_pct": 40}).json()["points"]
        acts = [p["action_kw"] for p in pts]
        assert all(later <= earlier + 1e-9 for earlier, later in zip(acts, acts[1:])), f"{sweep}: {acts}"
    price_pts = client.post("/api/analysis/sensitivity", json={"sweep": "price", "horizon_slots": 8}).json()["points"]
    assert len({p["level"] for p in price_pts}) <= 3, "price is bucketed into 3 levels, so the curve is a step function"


# ── digital twin ──────────────────────────────────────────────────────────
def test_twin_lanes_share_the_same_world_and_obey_physics(client):  # noqa: F811
    t = client.post("/api/twin/run", json={"horizon_slots": 12, "seed": 3}).json()
    sdp, fast = t["lanes"]["sdp"]["records"], t["lanes"]["charge_immediately"]["records"]
    assert len(sdp) == len(fast) == 12
    for a, b in zip(sdp, fast):   # identical price / grid / solar path in both lanes
        assert (a["price_level"], a["grid_level"], a["solar_level"]) == (b["price_level"], b["grid_level"], b["solar_level"])
    for lane in (sdp, fast):
        socs = [r["soc_after_pct"] for r in lane]
        assert all(0 <= s <= 100 for s in socs) and socs == sorted(socs), "charging never lowers SOC"
        costs = [r["cumulative_cost_inr"] for r in lane]
        assert costs == sorted(costs)
        assert all(r["delivered_kw"] <= r["action_kw"] + 1e-9 for r in lane)
    assert t["lanes"]["charge_immediately"]["final_soc_pct"] >= t["lanes"]["sdp"]["final_soc_pct"] - 1e-9


# ── fleet ─────────────────────────────────────────────────────────────────
def _fleet_body(n=8, grid=60.0):
    return {"vehicles": [{"vehicle_id": i, "name": f"EV{i}", "current_soc_pct": 20 + 5 * i, "urgency": 1 + i % 5} for i in range(n)],
            "chargers": [{"charger_id": 1, "power_kw": 50}, {"charger_id": 2, "power_kw": 22}], "grid_capacity_kw": grid}


def test_fleet_allocation_never_violates_a_constraint(client):  # noqa: F811
    r = client.post("/api/fleet/allocate", json=_fleet_body()).json()
    assert r["constraint_violations"] == []
    assert r["totals"]["grid_used_kw"] <= r["totals"]["grid_capacity_kw"] + 1e-6
    # each charger is a power pool: its TOTAL load stays within its rating, and the per-charger
    # vehicle lists agree with the per-vehicle assignments
    for c in r["chargers"]:
        assert c["allocated_kw"] <= c["power_kw"] + 1e-6
        assert sorted(c["vehicle_ids"]) == sorted(v["vehicle_id"] for v in r["vehicles"] if v["charger_id"] == c["charger_id"])
        assert c["allocated_kw"] == pytest.approx(sum(v["allocated_kw"] for v in r["vehicles"] if v["charger_id"] == c["charger_id"]))
    assert sum(len(c["vehicle_ids"]) for c in r["chargers"]) == r["totals"]["vehicles_charging"]
    assert len({c["allocated_kw"] for c in r["chargers"]}) >= 1
    assert all(v["status"] == "waiting" for v in r["vehicles"] if v["charger_id"] is None and v["needs_kwh"] > 0)


def test_fleet_prioritises_urgent_vehicles(client):  # noqa: F811
    r = client.post("/api/fleet/allocate", json=_fleet_body()).json()
    assert r["service_score_pct"]["optimised"] >= r["service_score_pct"]["first_come_first_served"]


def test_fleet_vehicle_at_target_and_validation(client):  # noqa: F811
    body = _fleet_body(2)
    body["vehicles"][0].update(current_soc_pct=95, target_soc_pct=80)
    rows = client.post("/api/fleet/allocate", json=body).json()["vehicles"]
    assert rows[0]["status"] == "at_target" and rows[0]["allocated_kw"] == 0
    dup = _fleet_body(2); dup["vehicles"][1]["vehicle_id"] = 0
    assert client.post("/api/fleet/allocate", json=dup).status_code == 422
    assert client.post("/api/fleet/allocate", json={**_fleet_body(2), "vehicles": []}).status_code == 422


# ── battery ───────────────────────────────────────────────────────────────
def test_battery_wear_grows_with_charge_power_and_is_u_shaped_in_temperature(client):  # noqa: F811
    r = client.get("/api/battery/curves", params={"max_charge_rate_kw": 50, "ambient_temp_c": 25}).json()
    power = [p["total"] for p in r["by_charge_power"]["points"]]
    assert power == sorted(power), "faster charging must never wear the battery less"
    temp = r["by_temperature"]["points"]
    coldest, hottest = temp[0]["total"], temp[-1]["total"]
    best = min(temp, key=lambda p: p["total"])
    assert 10 <= best["x"] <= 30 and coldest > best["total"] and hottest > best["total"]
    health = [p["health_pct"] for p in r["health_indicator"]["points"]]
    assert health == sorted(health, reverse=True) and health[0] == 100.0
