# Change log: what was done to the originally supplied project

This file is generated from a real comparison of `ev-optigrid.zip` (as originally supplied) with the delivered project. **66 files added, 40 modified, 0 removed.** Nothing you supplied was deleted.

## Summary

**1. Making the backend actually work.** It had only ever been syntax-checked. Run for real, it had bugs that stopped it working at all
(unpinned `bcrypt` broke login, a missing dependency stopped startup, UUID keys couldn't be stored on SQLite, `/charging/optimize`
and `/stations/nearby` crashed, journeys returned no id, and more). All fixed, with tests. Bug table: `docs/TESTING.md`, bugs 1 to 19.

**2. Fixing the optimiser's infrastructure.** The solved-policy cache could be corrupted by a partial write and then crash every request;
the simulator's cost model contradicted its documentation and hung on default settings; ML model files had the same partial-write
problem. All fixed (atomic writes, recovery, work limits), and an in-memory LRU cache added in front of the disk cache.

**3. Security.** No endpoint checked a token. Now: JWT access and refresh tokens, owner-only vehicles / journeys / results, refresh
tokens rejected as access tokens, a startup guard against the default secret in production. 28 tests.

**4. A real frontend.** `frontend/app`, `components`, `charts`, `services` were empty folders. Built a Next.js 14 + TypeScript app:
sign-in, overview, smart charging (with live re-optimisation), journey planner, stations, copilot, fleet, digital twin, simulator,
battery health, and five pages that explain the optimiser (state space, policy heatmap, Bellman equation, Monte Carlo, sensitivity), with
a Leaflet map. The standalone `frontend/webapp/` you supplied is kept untouched.

**5. Features from the synopsis that were missing.** Monitor and re-optimise loop (`/api/charging/monitor`), digital twin, fleet
allocation endpoint, battery curves, APScheduler background warm-up, Leaflet map, in-memory LRU cache, Vitest tests.

**6. Running on a laptop.** `setup.sh|bat`, `start.sh|bat`, `RUN_ON_YOUR_LAPTOP.md`; `.env.example` now defaults to SQLite (it defaulted to
PostgreSQL, which broke first run); XGBoost load failures (macOS) now fall back instead of crashing; Python/Node version checks.

**7. Documentation.** New: `RUN_ON_YOUR_LAPTOP.md`, `docs/SYNOPSIS_TRACEABILITY.md`, `frontend/README.md`, this file. Rewritten or
corrected: `README.md`, `docs/HANDOFF.md`, `docs/TESTING.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/SETUP.md`, `docs/SIMULATION.md`
(an incorrect scaling claim), `docs/VIVA_GUIDE.md`.

**Tests:** 163 (as supplied, per its own notes) -> **289 backend + 23 frontend + 36 live end-to-end**.

**Nothing from the supplied files was removed.** The only behavioural changes to supplied code are the fixes listed in
`docs/TESTING.md` and: `POST /api/vehicles` and `GET /api/vehicles` no longer take a trusted `user_id`; most endpoints now require login;
`/api/simulation/run` refuses over-budget runs and has smaller defaults; the policy and ML caches write atomically.


## Files modified (40)

Lines added / removed against the original.


**(project root)**

- `.gitignore`  (+15 / -0)
- `README.md`  (+49 / -68)

**backend**

- `backend/.env.example`  (+13 / -3)
- `backend/api/auth.py`  (+23 / -0)
- `backend/api/charging.py`  (+80 / -10)
- `backend/api/copilot.py`  (+15 / -5)
- `backend/api/journeys.py`  (+8 / -5)
- `backend/api/predictions.py`  (+2 / -2)
- `backend/api/simulation.py`  (+35 / -6)
- `backend/api/vehicles.py`  (+20 / -11)
- `backend/database/config.py`  (+13 / -1)
- `backend/main.py`  (+25 / -3)
- `backend/models/charging_session.py`  (+2 / -2)
- `backend/models/energy.py`  (+8 / -8)
- `backend/models/journey.py`  (+4 / -4)
- `backend/models/misc.py`  (+2 / -2)
- `backend/models/optimization.py`  (+10 / -7)
- `backend/models/prediction.py`  (+2 / -2)
- `backend/models/station.py`  (+4 / -4)
- `backend/models/user.py`  (+2 / -2)
- `backend/models/vehicle.py`  (+2 / -2)
- `backend/requirements.txt`  (+2 / -0)
- `backend/schemas/charging.py`  (+1 / -0)
- `backend/schemas/stations.py`  (+1 / -0)
- `backend/services/auth_service.py`  (+3 / -3)
- `backend/services/station_service.py`  (+9 / -3)

**docs**

- `docs/API.md`  (+56 / -8)
- `docs/ARCHITECTURE.md`  (+6 / -0)
- `docs/HANDOFF.md`  (+64 / -106)
- `docs/SETUP.md`  (+17 / -20)
- `docs/SIMULATION.md`  (+11 / -4)
- `docs/TESTING.md`  (+97 / -31)
- `docs/VIVA_GUIDE.md`  (+14 / -1)

**ml**

- `ml/demand_predictor.py`  (+2 / -2)
- `ml/grid_forecaster.py`  (+2 / -2)
- `ml/model_utils.py`  (+42 / -1)
- `ml/price_forecaster.py`  (+2 / -2)
- `ml/queue_predictor.py`  (+2 / -2)
- `ml/solar_forecaster.py`  (+2 / -2)

**optimization**

- `optimization/policy.py`  (+95 / -11)

## Files added (66, about 8,077 lines)


**(project root)**  (5)

- `RUN_ON_YOUR_LAPTOP.md`  (123 lines)
- `setup.bat`  (32 lines)
- `setup.sh`  (30 lines)
- `start.bat`  (12 lines)
- `start.sh`  (14 lines)

**backend**  (10)

- `backend/api/analysis.py`  (51 lines)
- `backend/api/battery.py`  (11 lines)
- `backend/api/deps.py`  (62 lines)
- `backend/api/fleet.py`  (12 lines)
- `backend/api/twin.py`  (12 lines)
- `backend/schemas/analysis.py`  (95 lines)
- `backend/services/analysis_service.py`  (385 lines)
- `backend/services/fleet_service.py`  (93 lines)
- `backend/services/monitor_service.py`  (64 lines)
- `backend/services/scheduler.py`  (61 lines)

**docs**  (1)

- `docs/SYNOPSIS_TRACEABILITY.md`  (70 lines)

**frontend**  (46)

- `frontend/.env.example`  (2 lines)
- `frontend/README.md`  (85 lines)
- `frontend/app/battery/page.tsx`  (66 lines)
- `frontend/app/copilot/page.tsx`  (98 lines)
- `frontend/app/fleet/page.tsx`  (108 lines)
- `frontend/app/globals.css`  (265 lines)
- `frontend/app/journey/page.tsx`  (175 lines)
- `frontend/app/layout.tsx`  (22 lines)
- `frontend/app/login/page.tsx`  (76 lines)
- `frontend/app/optimiser/bellman/page.tsx`  (94 lines)
- `frontend/app/optimiser/monte-carlo/page.tsx`  (84 lines)
- `frontend/app/optimiser/policy/page.tsx`  (78 lines)
- `frontend/app/optimiser/sensitivity/page.tsx`  (65 lines)
- `frontend/app/optimiser/state-space/page.tsx`  (129 lines)
- `frontend/app/page.tsx`  (79 lines)
- `frontend/app/simulator/page.tsx`  (93 lines)
- `frontend/app/smart-charging/page.tsx`  (154 lines)
- `frontend/app/stations/page.tsx`  (106 lines)
- `frontend/app/twin/page.tsx`  (98 lines)
- `frontend/charts/Heatmap.tsx`  (47 lines)
- `frontend/charts/Histogram.tsx`  (36 lines)
- `frontend/charts/LineChart.tsx`  (55 lines)
- `frontend/charts/MetricBars.tsx`  (22 lines)
- `frontend/charts/color.ts`  (18 lines)
- `frontend/components/AuthProvider.tsx`  (64 lines)
- `frontend/components/LeafletMap.tsx`  (52 lines)
- `frontend/components/MapPanel.tsx`  (34 lines)
- `frontend/components/MapView.tsx`  (85 lines)
- `frontend/components/MonitorPanel.tsx`  (106 lines)
- `frontend/components/PolicyControls.tsx`  (44 lines)
- `frontend/components/Shell.tsx`  (107 lines)
- `frontend/components/TwinLane.tsx`  (84 lines)
- `frontend/components/ui.tsx`  (106 lines)
- `frontend/hooks/useRun.ts`  (17 lines)
- `frontend/hooks/useVehicles.ts`  (49 lines)
- `frontend/next.config.mjs`  (20 lines)
- `frontend/package-lock.json`  (2434 lines)
- `frontend/package.json`  (28 lines)
- `frontend/scripts/e2e-live.ts`  (120 lines)
- `frontend/services/api.ts`  (351 lines)
- `frontend/services/auth.ts`  (38 lines)
- `frontend/services/defaults.ts`  (30 lines)
- `frontend/tests/api-client.test.ts`  (94 lines)
- `frontend/tests/charts.test.tsx`  (93 lines)
- `frontend/tsconfig.json`  (21 lines)
- `frontend/vitest.config.ts`  (8 lines)

**tests**  (4)

- `tests/backend/test_analysis_api.py`  (217 lines)
- `tests/backend/test_api_endpoints.py`  (459 lines)
- `tests/backend/test_scheduler_and_ml_safety.py`  (91 lines)
- `tests/optimization/test_policy_cache.py`  (143 lines)

## Files removed

None.
