# Architecture

## System diagram

```
                         ┌─────────────────────────┐
                         │        Next.js UI        │
                         │ Dashboard / Map / Copilot│
                         └────────────┬─────────────┘
                                      │ REST (JSON)
                         ┌────────────▼─────────────┐
                         │        FastAPI Backend    │
                         │  services/ (business logic)│
                         └───┬─────────┬─────────┬───┘
                             │         │         │
                 ┌───────────▼──┐ ┌────▼────┐ ┌──▼────────────┐
                 │ Optimization  │ │   ML    │ │  Providers     │
                 │ (MDP/SDP,     │ │ (price, │ │ (Location,     │
                 │ multi-obj,    │ │ grid,   │ │  Station,      │
                 │ COS, battery) │ │ solar,  │ │  Routing) —    │
                 │               │ │ queue)  │ │ real or demo   │
                 └───────┬───────┘ └────┬────┘ └───────┬───────┘
                         │              │              │
                         └──────┬───────┴──────┬───────┘
                                │              │
                         ┌──────▼──────────────▼──────┐
                         │        PostgreSQL           │
                         └──────────────────────────────┘
```

## Technology stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind | SSR, type safety, fast iteration |
| Maps | Leaflet/MapLibre via `MapProvider` abstraction | Provider-agnostic |
| Backend | Python FastAPI | Async, integrates cleanly with ML/optimization |
| DB | PostgreSQL + SQLAlchemy + Alembic | Relational integrity, versioned schema |
| Optimization | NumPy/SciPy hand-rolled MDP + value iteration | Explainable at the viva; no RL black box |
| ML | XGBoost / scikit-learn | Practical, fast to train, interpretable |
| Auth | JWT + bcrypt | Standard |
| IoT (optional) | MQTT + simulated ESP32 telemetry | |
| Testing | pytest / Vitest | |

## Provider abstraction (§39)

External integrations (maps, routing, charging-station discovery, weather,
LLM) are never called directly from business logic. Each has an interface
with a `Real*` and `Demo*` implementation, chosen at startup from
environment variables (`backend/database/config.py::Settings`). If no keys
are configured, the whole system runs in **DEMO MODE** automatically and
every affected API response is tagged `source: demo`. See
`docs/LOCATION_SERVICES.md`.

## Optimization pipeline

```
1. Journey energy model  → energy_required, expected_arrival_soc, minimum_safe_soc
2. Station discovery     → nearby + along-route stations (ChargingStationProvider)
3. Per-station forecasts → price / grid / solar / queue (ml/*_forecaster.py)
4. Charging Opportunity Score per station (optimization/station_optimizer.py)
5. Feasibility check     → is the deadline achievable at all? → urgent-mode branch if not
6. State construction    → SDP policy lookup (optimization/policy.py)
7. Multi-objective cost evaluated for top-N (station, action-sequence) candidates
8. Best plan selected per active profile/weights
9. Explanation rows generated from the same variables (never invented)
10. Persisted: optimization_runs → optimization_results → optimization_explanations
```

Re-optimization (§12) re-enters at step 3/6 on a trigger (price/grid/queue
change, deadline change, station unavailable). It always creates a *new*
`optimization_run` row and diffs the new result against the previous one —
nothing is edited in place (see `docs/DATABASE.md`).

## Folder structure

```
ev-optigrid/
├── frontend/            Next.js UI
├── backend/
│   ├── api/             FastAPI routers (thin — no business logic)
│   ├── services/        location_service, optimization_service, ...
│   ├── models/          SQLAlchemy ORM
│   ├── schemas/         Pydantic request/response models
│   ├── database/        settings + session/engine
│   └── alembic/         migrations
├── optimization/        mdp.py, value_iteration.py, station_optimizer.py, ...
├── ml/                  price_forecaster.py, grid_forecaster.py, ...
├── simulation/          ev_simulator.py, baseline_policies.py, experiment_runner.py
├── data/                synthetic/, seeds/  (all labeled)
├── docs/                this file + ALGORITHM.md, MDP.md, VIVA_GUIDE.md, ...
└── tests/               mirrors backend/optimization/ml
```

## Development phases

1. Architecture + folders — **done**
2. Database + models — **done** (models + Alembic scaffold; migration
   generated once dependencies are installed locally, see `docs/SETUP.md`)
3. EV/battery simulation
4. MDP + stochastic model
5. Value iteration / SDP
6. Baseline policies (greedy, fixed, threshold, priority)
7. Simulation engine (What-If Simulator backend)
8. ML forecasting (price/grid/solar/queue/demand)
9. Charging Opportunity Score
10. Location + station provider abstraction
11. Journey/route energy model
12. FastAPI backend (full API surface)
13. Frontend
14. Map interface
15. AI Copilot
16. Real-time re-optimization
17. Fleet optimization
18. Research dashboard
19. Testing
20. Documentation
21. Demo mode

Each phase ends with: syntax/import verification, calculation spot-checks,
and the project kept runnable.

> **Status.** The list above is the planned roadmap. As delivered: algorithms, ML, simulation, the backend API (33 endpoints,
> JWT login with owner-only data), a 15-page Next.js frontend wired to it (including the map, digital twin, fleet dashboard and the
> pages that explain the optimiser), and the documentation are built and tested. Not built: real (non-demo) data providers
> exercised end to end, PostgreSQL verification, rate limiting, and the optional MQTT/ESP32 telemetry wiring. Not verified by
> anyone yet: how the pages look in a real browser. See `docs/HANDOFF.md` and `docs/SYNOPSIS_TRACEABILITY.md`.
