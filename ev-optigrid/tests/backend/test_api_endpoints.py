"""
End-to-end tests of the FastAPI layer, using a throwaway SQLite database.

These exist because the backend was written in an environment with no network
(nothing could be installed or executed). The first time it was actually run,
it turned up real bugs; each `test_regression_*` below pins one of them:

  1. UUID primary keys could not be bound by SQLite (register -> 500)
  2. POST /charging/optimize crashed: optimization_runs.journey_id was NOT NULL
     even though the endpoint is documented as callable without a journey
  3. GET /stations/nearby crashed when the queue model wasn't trained yet
     (the try/except FileNotFoundError wrapped the import, which never raises)
  4. POST /journeys, /charging/optimize returned no IDs, so /reoptimize,
     /schedule and /explanation were unreachable through the API alone
  5. POST /journeys with an unknown vehicle_id crashed (AttributeError -> 500)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Never write trained-model artifacts into the repo from a test run.
    from ml import price_forecaster, grid_forecaster, solar_forecaster, queue_predictor
    for module in (price_forecaster, grid_forecaster, solar_forecaster, queue_predictor):
        monkeypatch.setattr(module, "ARTIFACT_PATH", tmp_path / Path(module.ARTIFACT_PATH).name)

    from database.session import Base, get_db
    import models  # noqa: F401  (registers all tables on Base.metadata)
    from main import app

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    c = TestClient(app)
    # Everything except health/auth/predictions/stations requires login, so the default
    # test client is a logged-in user. Use `anonymous_client` / `second_user_client` otherwise.
    tokens = c.post("/api/auth/register", json={"email": "fixture-user@evoptigrid.dev",
                                                "password": "password123", "name": "Fixture"}).json()
    c.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    c.tokens = tokens
    yield c
    app.dependency_overrides.clear()
    engine.dispose()


OPTIMIZE_BODY = {
    "battery_capacity_kwh": 60.0, "max_charge_rate_kw": 50.0, "current_soc_pct": 32.0,
    "target_soc_pct": 90.0, "minimum_safe_soc_pct": 70.0, "horizon_slots": 24, "slot_minutes": 15,
    "current_price_per_kwh": 8.0, "current_grid_load_pct": 60.0,
    "current_solar_availability_frac": 0.2, "profile": "balanced",
}


def _register(client, email="a@b.com"):
    r = client.post("/api/auth/register", json={"email": email, "password": "password123", "name": "Asha"})
    assert r.status_code == 201, r.text
    return r.json()


def _make_vehicle(client):
    user_id = client.get("/api/auth/me").json()["id"]
    r = client.post("/api/vehicles", json={
        "make": "Tata", "model": "Nexon EV", "battery_capacity_kwh": 40.5,
        "efficiency_kwh_per_km": 0.16, "max_charge_rate_kw": 50, "current_soc": 32})
    assert r.status_code == 201, r.text
    return user_id, r.json()["id"]


def _journey_body(vehicle_id):
    return {"origin_lat": 28.61, "origin_lng": 77.21, "dest_lat": 27.18, "dest_lng": 78.02,
            "vehicle_id": vehicle_id, "target_soc_pct": 90}


# ── health ────────────────────────────────────────────────────────────────
def test_health_endpoints(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health/db").json()["database"] == "connected"


# ── auth ──────────────────────────────────────────────────────────────────
def test_regression_register_works_on_sqlite_and_returns_string_subject(client):
    """Bug 1: UUID PKs broke SQLite. The JWT `sub` must also be a plain string."""
    from jose import jwt
    tokens = _register(client)
    assert tokens["token_type"] == "bearer"
    assert isinstance(jwt.get_unverified_claims(tokens["access_token"])["sub"], str)


def test_register_duplicate_email_is_409(client):
    _register(client)
    r = client.post("/api/auth/register", json={"email": "a@b.com", "password": "password123", "name": "x"})
    assert r.status_code == 409


def test_login_success_and_failure(client):
    _register(client)
    assert client.post("/api/auth/login", json={"email": "a@b.com", "password": "password123"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrongwrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@b.com", "password": "password123"}).status_code == 401


def test_register_validation(client):
    assert client.post("/api/auth/register", json={"email": "not-an-email", "password": "password123", "name": "x"}).status_code == 422
    assert client.post("/api/auth/register", json={"email": "z@z.com", "password": "short", "name": "x"}).status_code == 422


# ── vehicles ──────────────────────────────────────────────────────────────
def test_vehicle_create_list_get(client):
    user_id, vehicle_id = _make_vehicle(client)
    assert isinstance(vehicle_id, str)
    listed = client.get("/api/vehicles").json()
    assert [v["id"] for v in listed] == [vehicle_id]
    assert client.get(f"/api/vehicles/{vehicle_id}").json()["model"] == "Nexon EV"
    assert client.get("/api/vehicles/does-not-exist").status_code == 404


# ── journeys ──────────────────────────────────────────────────────────────
def test_regression_journey_returns_id_and_flags_infeasible_trip(client):
    """Bug 4: journey_id must be returned. Delhi->Agra on 32% of 40 kWh needs a charge."""
    _, vehicle_id = _make_vehicle(client)
    body = client.post("/api/journeys", json=_journey_body(vehicle_id)).json()
    assert body["journey_id"]
    assert body["is_feasible_without_charging"] is False
    assert body["route_source"] == "demo"


def test_regression_journey_unknown_vehicle_is_404_not_500(client):
    """Bug 5."""
    r = client.post("/api/journeys", json=_journey_body("no-such-vehicle"))
    assert r.status_code == 404


# ── charging ──────────────────────────────────────────────────────────────
def test_regression_optimize_standalone_without_journey(client):
    """Bug 2: standalone /optimize must persist without a journey_id, and return a result_id."""
    r = client.post("/api/charging/optimize", json=OPTIMIZE_BODY)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result_id"]
    assert body["recommended_action"] in {"wait", "charge_now", "charge_partial", "no_action_needed"}
    assert body["reasons"], "every recommendation must come with at least one reason"


def test_optimize_rejects_bad_input(client):
    assert client.post("/api/charging/optimize", json={**OPTIMIZE_BODY, "profile": "nonsense"}).status_code == 422
    assert client.post("/api/charging/optimize", json={**OPTIMIZE_BODY, "current_soc_pct": 150}).status_code == 422


def test_optimize_reoptimize_schedule_explanation_chain(client):
    """Bug 4 end-to-end: journey -> reoptimize -> schedule -> explanation, with stale-marking."""
    _, vehicle_id = _make_vehicle(client)
    journey_id = client.post("/api/journeys", json=_journey_body(vehicle_id)).json()["journey_id"]

    first = client.post("/api/charging/reoptimize", params={"journey_id": journey_id}, json=OPTIMIZE_BODY)
    assert first.status_code == 200, first.text
    second = client.post("/api/charging/reoptimize", params={"journey_id": journey_id},
                         json={**OPTIMIZE_BODY, "current_price_per_kwh": 12.0})
    assert second.status_code == 200, second.text
    assert first.json()["result_id"] != second.json()["result_id"]

    # /schedule returns the latest NON-stale result, i.e. the second one.
    schedule = client.get("/api/charging/schedule", params={"journey_id": journey_id}).json()
    assert schedule["result_id"] == second.json()["result_id"]

    explanation = client.get("/api/charging/explanation", params={"result_id": schedule["result_id"]})
    assert explanation.status_code == 200
    assert explanation.json()["reasons"]


def test_schedule_and_explanation_404_for_unknown_ids(client):
    assert client.get("/api/charging/schedule", params={"journey_id": "nope"}).status_code == 404
    assert client.get("/api/charging/explanation", params={"result_id": "nope"}).status_code == 404


# ── stations ──────────────────────────────────────────────────────────────
def test_regression_stations_nearby_trains_queue_model_on_demand(client):
    """Bug 3: previously a 500 whenever the queue model hadn't been trained yet."""
    r = client.get("/api/stations/nearby", params={"lat": 28.61, "lng": 77.21, "radius_km": 10})
    assert r.status_code == 200, r.text
    stations = r.json()
    stations = stations if isinstance(stations, list) else stations["stations"]
    assert stations
    scores = [s["cos_score"] for s in stations]
    assert scores == sorted(scores, reverse=True), "stations must be ranked by COS, best first"
    assert all(s["source"] for s in stations), "spec §29: every station must carry a data-source label"


def test_stations_route(client):
    r = client.get("/api/stations/route", params={
        "origin_lat": 28.61, "origin_lng": 77.21, "dest_lat": 28.46, "dest_lng": 77.03})
    assert r.status_code == 200
    assert r.json()["route"]["source"] == "demo"


# ── copilot / predictions / simulation ────────────────────────────────────
def test_copilot_parse(client):
    r = client.post("/api/copilot/parse", json={"message": "I need to reach Agra by 6pm with 80% charge"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_valid"] is True
    assert body["extracted_target_soc_pct"] == 80.0


@pytest.mark.parametrize("path,key", [
    ("/api/predictions/prices", "predicted_price_per_kwh"),
    ("/api/predictions/grid", "predicted_grid_load_pct"),
    ("/api/predictions/solar", "predicted_generation_kwh"),
    ("/api/predictions/queue", "predicted_queue"),
])
def test_predictions_are_labelled_as_predicted(client, path, key):
    body = client.get(path).json()
    assert key in body
    assert body["source"] == "predicted"


def test_simulation_run_and_fetch_results(client):
    run = client.post("/api/simulation/run", json={"num_evs": 8, "n_replications": 2, "horizon_slots": 24})
    assert run.status_code == 200, run.text
    experiment_id = run.json()["experiment_id"]
    results = client.get("/api/simulation/results", params={"experiment_id": experiment_id})
    assert results.status_code == 200
    assert len(results.json()) >= 2


# ── simulator cost guard (found when the frontend first ran default settings) ──
def test_regression_simulation_rejects_runs_that_would_take_minutes(client):
    """A 25-car x 5-rep x 48-slot run solved >3,000 policies and ran >5 minutes before
    the proxy gave up. It must now be refused immediately, with a message saying why."""
    r = client.post("/api/simulation/run", json={"num_evs": 25, "n_replications": 5, "horizon_slots": 48})
    assert r.status_code == 422
    assert "limit" in r.json()["detail"].lower()


def test_simulation_default_request_is_within_the_budget(client):
    from api.simulation import SimulationRequest, MAX_SIM_WORK, estimated_work
    d = SimulationRequest()
    assert estimated_work(d.num_evs, d.n_replications, d.horizon_slots) <= MAX_SIM_WORK


def test_simulation_limits_endpoint(client):
    body = client.get("/api/simulation/limits").json()
    assert body["max_work"] > 0 and body["solves_per_second_cold"] > 0


def test_guard_only_applies_to_runs_that_use_the_sdp(client):
    """Cheap baselines scale fine, so a big fleet is allowed when the SDP isn't in the mix."""
    r = client.post("/api/simulation/run", json={
        "num_evs": 60, "n_replications": 2, "horizon_slots": 48, "algorithms": ["greedy", "priority"]})
    assert r.status_code == 200, r.text


# ══ authentication & authorisation ═══════════════════════════════════════
@pytest.fixture()
def anonymous_client(client):
    from main import app
    return TestClient(app)          # same app + test DB, but no token


@pytest.fixture()
def second_user_client(client):
    from main import app
    other = TestClient(app)
    tokens = other.post("/api/auth/register", json={"email": "other@evoptigrid.dev",
                                                    "password": "password123", "name": "Other"}).json()
    other.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    other.tokens = tokens
    return other


PROTECTED = [
    ("get", "/api/auth/me", None),
    ("post", "/api/vehicles", {"make": "a", "model": "b", "battery_capacity_kwh": 40, "efficiency_kwh_per_km": 0.16, "max_charge_rate_kw": 50}),
    ("get", "/api/vehicles", None),
    ("get", "/api/vehicles/x", None),
    ("post", "/api/journeys", {"origin_lat": 1, "origin_lng": 1, "dest_lat": 2, "dest_lng": 2, "vehicle_id": "x"}),
    ("post", "/api/charging/optimize", OPTIMIZE_BODY),
    ("post", "/api/charging/reoptimize?journey_id=x", OPTIMIZE_BODY),
    ("get", "/api/charging/schedule?journey_id=x", None),
    ("get", "/api/charging/explanation?result_id=x", None),
    ("post", "/api/copilot/parse", {"message": "hi"}),
    ("post", "/api/simulation/run", {"num_evs": 2, "n_replications": 1, "horizon_slots": 4, "algorithms": ["greedy"]}),
    ("get", "/api/simulation/limits", None),
]


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_regression_protected_endpoints_reject_anonymous_requests(anonymous_client, method, path, body):
    """Previously NO endpoint checked a token, so anyone could read any user's vehicles."""
    r = getattr(anonymous_client, method)(path, **({"json": body} if body is not None else {}))
    assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"
    assert r.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize("path", [
    "/health", "/api/predictions/prices", "/api/predictions/grid", "/api/predictions/solar",
    "/api/predictions/queue", "/api/stations/nearby?lat=28.6&lng=77.2"])
def test_public_endpoints_stay_open(anonymous_client, path):
    assert anonymous_client.get(path).status_code == 200


def test_garbage_and_expired_tokens_are_rejected(anonymous_client):
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from database.config import get_settings
    cfg = get_settings()

    assert anonymous_client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401
    expired = jwt.encode({"sub": "x", "type": "access", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                         cfg.jwt_secret_key, algorithm=cfg.jwt_algorithm)
    assert anonymous_client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    forged = jwt.encode({"sub": "x", "type": "access", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        "some-other-secret", algorithm=cfg.jwt_algorithm)
    assert anonymous_client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_token_for_a_deleted_account_is_rejected(anonymous_client):
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from database.config import get_settings
    cfg = get_settings()
    ghost = jwt.encode({"sub": "no-such-user", "type": "access", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                       cfg.jwt_secret_key, algorithm=cfg.jwt_algorithm)
    assert anonymous_client.get("/api/auth/me", headers={"Authorization": f"Bearer {ghost}"}).status_code == 401


def test_refresh_token_cannot_be_used_as_an_access_token(client, anonymous_client):
    r = anonymous_client.get("/api/auth/me", headers={"Authorization": f"Bearer {client.tokens['refresh_token']}"})
    assert r.status_code == 401
    assert "token type" in r.json()["detail"].lower()


def test_refresh_flow_and_me(client, anonymous_client):
    assert client.get("/api/auth/me").json()["email"] == "fixture-user@evoptigrid.dev"
    r = anonymous_client.post("/api/auth/refresh", json={"refresh_token": client.tokens["refresh_token"]})
    assert r.status_code == 200
    new_access = r.json()["access_token"]
    assert anonymous_client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_access}"}).status_code == 200
    # an access token is not a refresh token
    bad = anonymous_client.post("/api/auth/refresh", json={"refresh_token": client.tokens["access_token"]})
    assert bad.status_code == 401


def test_regression_users_cannot_see_or_use_each_others_data(client, second_user_client):
    """Cross-user isolation on every resource. Foreign ids must look identical to unknown ids (404)."""
    _, vehicle_id = _make_vehicle(client)
    journey_id = client.post("/api/journeys", json=_journey_body(vehicle_id)).json()["journey_id"]
    result_id = client.post("/api/charging/reoptimize", params={"journey_id": journey_id},
                            json=OPTIMIZE_BODY).json()["result_id"]
    other = second_user_client

    assert other.get(f"/api/vehicles/{vehicle_id}").status_code == 404
    assert other.get("/api/vehicles").json() == []
    assert other.post("/api/journeys", json=_journey_body(vehicle_id)).status_code == 404
    assert other.post("/api/charging/reoptimize", params={"journey_id": journey_id}, json=OPTIMIZE_BODY).status_code == 404
    assert other.get("/api/charging/schedule", params={"journey_id": journey_id}).status_code == 404
    assert other.get("/api/charging/explanation", params={"result_id": result_id}).status_code == 404
    assert other.post("/api/copilot/parse", json={"message": "charge to 80%", "vehicle_id": vehicle_id}).status_code == 404
    # ...while the owner still can
    assert client.get("/api/charging/explanation", params={"result_id": result_id}).status_code == 200


def test_standalone_optimize_results_are_owner_only(client, second_user_client):
    result_id = client.post("/api/charging/optimize", json=OPTIMIZE_BODY).json()["result_id"]
    assert second_user_client.get("/api/charging/explanation", params={"result_id": result_id}).status_code == 404
    assert client.get("/api/charging/explanation", params={"result_id": result_id}).status_code == 200


def test_cannot_create_a_vehicle_for_another_user(client, second_user_client):
    other_id = second_user_client.get("/api/auth/me").json()["id"]
    r = client.post("/api/vehicles", json={"user_id": other_id, "make": "a", "model": "b", "battery_capacity_kwh": 40,
                                            "efficiency_kwh_per_km": 0.16, "max_charge_rate_kw": 50})
    assert r.status_code == 403
    assert client.get("/api/vehicles", params={"user_id": other_id}).status_code == 403


def test_regression_reoptimize_unknown_journey_is_404(client):
    """Previously created an orphan run for ANY journey_id (SQLite doesn't enforce the FK)."""
    r = client.post("/api/charging/reoptimize", params={"journey_id": "no-such-journey"}, json=OPTIMIZE_BODY)
    assert r.status_code == 404


def test_copilot_uses_the_real_vehicle_when_given(client):
    _, vehicle_id = _make_vehicle(client)
    r = client.post("/api/copilot/parse", json={"message": "I need 80% by 6pm", "vehicle_id": vehicle_id})
    assert r.status_code == 200 and r.json()["is_valid"] is True


def test_production_refuses_the_default_jwt_secret():
    from database.config import Settings, DEFAULT_JWT_SECRET
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        Settings(environment="production", jwt_secret_key=DEFAULT_JWT_SECRET).assert_safe_for_environment()
    Settings(environment="production", jwt_secret_key="x" * 48).assert_safe_for_environment()   # fine
    Settings(environment="development").assert_safe_for_environment()                           # fine


# ══ monitoring & re-optimisation (synopsis workflow) ═════════════════════
def _monitor_body(**changes):
    return {"previous": OPTIMIZE_BODY, "current": {**OPTIMIZE_BODY, **changes}}


def test_monitor_ignores_small_changes(client):
    r = client.post("/api/charging/monitor", json=_monitor_body(current_price_per_kwh=8.5, current_grid_load_pct=63)).json()
    assert r["changed"] is False and r["triggers"] == [] and r["stored"] is False


@pytest.mark.parametrize("change,code", [
    ({"current_price_per_kwh": 12.0}, "price_change"),
    ({"current_grid_load_pct": 85.0}, "grid_change"),
    ({"current_solar_availability_frac": 0.8}, "solar_change"),
    ({"horizon_slots": 16}, "deadline_change"),
    ({"target_soc_pct": 70.0}, "target_change"),
])
def test_monitor_detects_each_material_change(client, change, code):
    r = client.post("/api/charging/monitor", json=_monitor_body(**change)).json()
    assert r["changed"] is True and code in [t["code"] for t in r["triggers"]]
    assert r["current"]["result_id"], "a changed situation must store a new plan"


def test_monitor_detects_queue_growth(client):
    body = {**_monitor_body(), "previous_queue_wait_min": 5, "current_queue_wait_min": 25}
    assert [t["code"] for t in client.post("/api/charging/monitor", json=body).json()["triggers"]] == ["queue_change"]
    body["current_queue_wait_min"] = 8   # a 3-minute wobble is not worth re-planning
    assert client.post("/api/charging/monitor", json=body).json()["changed"] is False


def test_monitor_stores_against_a_journey_and_marks_the_old_plan_stale(client):
    _, vehicle_id = _make_vehicle(client)
    journey_id = client.post("/api/journeys", json=_journey_body(vehicle_id)).json()["journey_id"]
    first = client.post("/api/charging/reoptimize", params={"journey_id": journey_id}, json=OPTIMIZE_BODY).json()
    r = client.post("/api/charging/monitor", json={**_monitor_body(current_price_per_kwh=14.0), "journey_id": journey_id}).json()
    assert r["changed"] and r["current"]["result_id"] != first["result_id"]
    assert client.get("/api/charging/schedule", params={"journey_id": journey_id}).json()["result_id"] == r["current"]["result_id"]


def test_monitor_respects_journey_ownership_and_login(client, second_user_client, anonymous_client):
    _, vehicle_id = _make_vehicle(client)
    journey_id = client.post("/api/journeys", json=_journey_body(vehicle_id)).json()["journey_id"]
    body = {**_monitor_body(current_price_per_kwh=14.0), "journey_id": journey_id}
    assert second_user_client.post("/api/charging/monitor", json=body).status_code == 404
    assert anonymous_client.post("/api/charging/monitor", json=body).status_code == 401
    assert client.get("/api/charging/monitor/thresholds").json()["price_pct"] == 15.0
