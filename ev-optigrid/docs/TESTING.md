# Testing

## Running the suite

```bash
cd backend && pip install -r requirements.txt
cd ..
pytest
```

## What's covered

**289 backend tests (pytest 8.3, Python 3.12), 23 frontend tests (Vitest 2), and a 36-check live end-to-end run.**

| Area | File | Count |
|---|---|---|
| Battery degradation model | `tests/optimization/test_battery_model.py` | 15 |
| MDP discretization | `tests/optimization/test_mdp.py` | 10 |
| Transition model | `tests/optimization/test_transition_model.py` | 7 |
| Reward/cost function | `tests/optimization/test_reward_model.py` | 12 |
| Value iteration (SDP) | `tests/optimization/test_value_iteration.py` | 7 |
| Policy cache (disk + in-memory LRU) | `tests/optimization/test_policy_cache.py` | 10 |
| Charging Opportunity Score | `tests/optimization/test_station_optimizer.py` | 13 |
| Explainability engine | `tests/optimization/test_explainability.py` | 11 |
| Multi-EV allocator | `tests/optimization/test_multi_ev_optimizer.py` | 12 |
| Fleet simulation | `tests/simulation/test_fleet_simulator.py` | 18 |
| ML forecasters | `tests/ml/test_ml_forecasters.py` | 12 |
| Providers + journey energy | `tests/backend/test_providers_and_journey.py` | 16 |
| AI Copilot | `tests/backend/test_copilot_service.py` | 23 |
| Optimization service | `tests/backend/test_optimization_service.py` | 7 |
| Auth service (hashing + JWT) | `tests/backend/test_auth_service.py` | 7 |
| **API: auth, isolation, charging, monitoring, stations, simulator** | `tests/backend/test_api_endpoints.py` | 61 |
| **API: analysis, digital twin, fleet, battery** | `tests/backend/test_analysis_api.py` | 41 |
| Scheduler + safe model training | `tests/backend/test_scheduler_and_ml_safety.py` | 7 |
| **Frontend: API client (token refresh, errors)** | `frontend/tests/api-client.test.ts` | 9 |
| **Frontend: charts and map** | `frontend/tests/charts.test.tsx` | 14 |

The new analysis tests assert properties of the mathematics rather than response shapes: the Bellman breakdown must
reproduce the solver's value function and action on seven different states; SOC interpolation must be unbiased; a full
battery must never charge; both digital-twin lanes must see the same price/grid/solar path; the fleet allocator must never
exceed a charger or the grid; faster charging must never wear the battery less; more expensive electricity or a more stressed
grid must never make the optimiser charge harder.

### How the tests were verified

The optimisation/ML/simulation code was first developed in a sandbox with no network access, using a lightweight
pytest-compatible stand-in. Everything was later run under real `pytest` with the versions pinned in
`backend/requirements.txt`, in a clean virtualenv, and against live `uvicorn` and Next.js servers.

### Frontend and end-to-end verification

- `npm run typecheck`, `npm run build` (16 routes), `npm test` (23 tests): all clean.
- `npm run e2e` runs the **real** `services/api.ts` against the live backend through the Next.js proxy, 36 checks: public endpoints,
  401 for anonymous callers, register / login / wrong password, transparent refresh of an expired access token, vehicles, journey,
  copilot, all five profiles, validation errors, monitoring (small change ignored, material change re-plans), state space, SOC
  interpolation, policy heatmap, Bellman check, Monte Carlo, all six sensitivity sweeps, digital twin, fleet, battery,
  simulator guard and run, sign-out, and the offline message.

### What is still NOT verified

- **How any page looks or behaves in a real browser.** No browser was available while building. Only the code, types, build,
  HTTP responses and API behaviour are verified. Open every page yourself.
- **The Leaflet street map** (needs a browser and internet) and the **Windows `.bat` scripts** (built on Linux).
- **PostgreSQL.** Everything ran on SQLite. The models use a native `UUID` there (`as_uuid=False`), never executed.
- **Non-demo providers** (Mapbox/OSRM/OpenChargeMap/OpenWeather/Anthropic). Only the `demo` provider stack has been run.
- **Load and security testing.** There is no rate limiting (the `rate_limit_per_minute` setting is not enforced) and tokens are
  kept in `localStorage` (readable by any script on the page; production should use an httpOnly cookie).
- **`npm audit`** reports advisories in Next.js 14.x that are only fixed by Next 16 (a breaking upgrade needing React 19). The app
  is pinned at the newest 14.x (14.2.35) and is meant to run locally, not be exposed to the internet, until that upgrade is done.

## Edge cases specifically covered (spec §35)

- SOC at 0% and 100% (value iteration correctly recommends 0 kW at 100%,
  after a real bug where it didn't — see `docs/MDP.md`)
- Target below current SOC (`greedy_policy`/`priority_policy` return 0 kW)
- Impossible deadline (`optimization_service` infeasibility path, urgent
  mode messaging)
- No available chargers / all chargers occupied (fleet simulator's waiting-
  slot accounting, multi-EV allocator's grid/charger capacity constraints)
- Grid overload (`grid_penalty` term, `validate_allocation`'s grid-capacity check)
- Very high electricity price (bucketized to the "high" price level, all
  cost-function tests exercise this bucket)
- Sudden price change (`Smart Charging` page's re-optimize control; backend
  `/api/charging/reoptimize`)
- Destination unreachable without charging (`estimate_journey_energy`'s
  `is_feasible_without_charging=False` path)

## Regression tests that exist specifically because of bugs found

These tests exist because they caught (or would have caught) a real bug,
not because they were written defensively in advance. That is worth
pointing out in a viva as evidence of adversarial testing.

**Algorithm / ML layer**

1. `test_value_iteration.py::test_full_soc_never_charges_further` — caught
   the `best_action_idx` indexing bug (docs/MDP.md §13b).
2. `test_fleet_simulator.py::test_greedy_and_priority_differ_under_real_contention`
   — caught greedy and priority baselines being accidentally identical.
3. `test_ml_forecasters.py::test_station_demand_has_queue_variance` — caught
   the R²≈0 synthetic-data generator bug (docs/ML.md).

**Backend layer** — found the first time the backend was actually executed
(it had only been syntax-checked before). Pinned in
`tests/backend/test_api_endpoints.py`; reverting the first seven fixes makes
8 of the tests fail.

| # | Bug | Symptom | Fix |
|---|---|---|---|
| 1 | `bcrypt` unpinned; `passlib 1.7.4` is incompatible with `bcrypt >= 4.1` | 5 auth tests failed; login/register would crash | pin `bcrypt==4.0.1` |
| 2 | `email-validator` missing from requirements | app failed at import (`EmailStr`) | add `email-validator==2.2.0` |
| 3 | UUID primary keys defaulted to `uuid.UUID` objects, which SQLite can't bind | `POST /auth/register` -> 500 | `PG_UUID(as_uuid=False)` + `str(uuid4())` defaults on all 16 tables |
| 4 | `optimization_runs.journey_id` was `NOT NULL`, but `/charging/optimize` is documented as standalone | `POST /charging/optimize` -> 500 | column nullable; profile string converted to the enum (422 if unknown) |
| 5 | `try/except FileNotFoundError` wrapped the *import* of the queue model, which never raises; the error occurs on model *load* | `GET /stations/nearby` -> 500 on a fresh install | train on first use, with a graceful fallback |
| 6 | Journey and optimize responses returned no IDs | `/reoptimize`, `/schedule`, `/explanation` unreachable via the API | return `journey_id` / `result_id` |
| 7 | `POST /journeys` didn't check the vehicle exists | unknown `vehicle_id` -> `AttributeError` -> 500 | 404 |
| 8 | **Policy cache wrote straight to its final filename** (`optimization/policy.py`); a reader arriving mid-write, or a killed process, left a truncated `.npz` and *every later request needing that policy crashed* with `BadZipFile` until the file was hand-deleted. Also loaded with `allow_pickle=True` | `POST /simulation/run` -> 500 | atomic write (temp file + `os.replace`), unreadable cache = miss and re-solve, `allow_pickle=False`. 5 tests in `test_policy_cache.py` (the two recovery tests fail on the old code; the concurrency test is only a smoke check) |
| 9 | Simulator scales as `cars × reps × slots` solves (cache key includes remaining horizon), contradicting the old claim in SIMULATION.md. Default 25×5×48 = 6,000 solves ran >5 min, wrote ~200 MB and made the Next.js proxy return a 500 | simulator page hung, then failed | API refuses runs over `SIM_MAX_WORK` (422, explained), smaller defaults, `/simulation/limits`, page shows an estimate first, proxy timeout raised to 300 s, docs corrected |
| 10 | **No endpoint checked a token.** `/register` and `/login` issued JWTs that nothing required, so anyone could read any user's vehicles by passing a `user_id` | data exposure | `Depends(get_current_user)` on everything except health, auth, predictions, stations; refresh tokens rejected as access tokens; owner-only vehicles / journeys / results (foreign ids give 404); 28 tests |
| 11 | `POST /charging/reoptimize` accepted **any** `journey_id`, including ones that don't exist (SQLite doesn't enforce the foreign key) | orphan rows | ownership check, 404 |
| 12 | The copilot ignored `vehicle_id` and always used a hard-coded 60 kWh car | wrong answers for real vehicles | uses the caller's own vehicle |
| 13 | ML model files were written straight to their final path, and two threads could train the same model at once | truncated model file, crash on every later call (same class as bug 8) | `atomic_dump` + lock-guarded `ensure_trained`; 7 tests |
| 14 | XGBoost installed but its native library missing (typical on macOS without `libomp`) raises an error the import fallback didn't catch | backend crash at startup | fallback catches any load failure, and says XGBoost was substituted |
| 15 | `backend/.env.example` defaulted to **PostgreSQL**, so `cp .env.example .env` on a laptop without it gave a broken backend | first run fails | SQLite default, PostgreSQL as a commented option |
| 16 | The policy cache key ignores the transition model, so a custom model silently got a policy solved for the default world | wrong policy | custom models bypass both caches; test |
| 17 | The built-in default JWT secret was accepted in any environment | forgeable tokens if deployed as-is | startup refuses it outside `development`; test |
| 18 | Fleet response listed only the first vehicle on a charger and its total load (found by a test while building the fleet page) | wrong charger view | all vehicles and the summed load reported |
| 19 | Next.js 14.2.15 had critical advisories | dependency risk | upgraded to 14.2.35; the remainder needs Next 16 (documented above) |

## Known warnings (not failures)

The suite emits ~290 warnings, almost all `datetime.utcnow()` deprecations (in the models, `station_service.py`,
`predictions.py` and inside `python-jose`) and pydantic v2 class-config deprecations. Harmless today; `utcnow()` will
eventually be removed from Python.
