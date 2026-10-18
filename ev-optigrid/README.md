# EV-OptiGrid

**An AI-Powered Personalized EV Charging, Route and Energy Optimization System**
(JIIT major project — Aditi Bhalla, Kashvi Rathore, Arav Gulati; supervisor Dr. Prashant Kaushik)

A journey-aware, personalized, stochastic charging decision-support system for electric vehicles. It is not a
charging-station directory: it answers *"given my battery, my journey, predicted grid and price conditions, and my
preferences, where, when, how much and how fast should I charge, and why?"*

## Run it on your laptop

**Read `RUN_ON_YOUR_LAPTOP.md`.** In short: install Python 3.12 and Node.js, run `setup.bat` (Windows) or
`./setup.sh` (Mac/Linux) once, then `start.bat` / `./start.sh`, and open http://localhost:3000.

## What is in it

| Area | What it does | Where |
|---|---|---|
| **Optimiser** | Stochastic dynamic programming (value iteration) over battery level and uncertain price, grid load and solar; five profiles; battery-wear aware; explains every decision | `optimization/` |
| **Prediction** | Price, grid load, solar, station queue and charging-demand models (XGBoost / random forest / gradient boosting), real held-out metrics, synthetic labelled data | `ml/` |
| **Stations** | Charging Opportunity Score ranking (cost, distance, speed, queue, battery impact, grid, renewables) | `optimization/station_optimizer.py` |
| **Backend** | FastAPI, 33 endpoints, JWT login with refresh, owner-only data, SQLAlchemy/Alembic, APScheduler warm-up | `backend/` |
| **Frontend** | Next.js 14 + TypeScript, 15 pages: smart charging with live re-optimisation, journey planner and map, stations, copilot, fleet, digital twin, simulator, battery health, and five pages that show *how the optimiser decides* | `frontend/` |
| **Simulation** | Fleet simulator comparing five policies with confidence intervals; Monte Carlo; digital twin | `simulation/`, `backend/services/analysis_service.py` |

Pages that explain the mathematics (for the viva): **State space**, **Policy heatmap**, **Bellman equation** (checks its own
arithmetic against the solver), **Monte Carlo**, **Sensitivity**.

## Honest status

- **Tested:** 289 backend tests (pytest), 23 frontend tests (Vitest), and a 36-check live end-to-end run against the real
  servers. Details and every bug found along the way: `docs/TESTING.md`.
- **Not verified by anyone yet:** how the pages *look* in a real browser; the Windows `.bat` scripts; PostgreSQL (SQLite is the
  default and is what was tested); real map/routing/station/LLM providers (demo providers only).
- **Synthetic data:** all ML training data, stations and routes are synthetic or demo unless API keys are configured, and every
  response is labelled with its `source`.
- **Differences from the synopsis** (Tailwind not used, no Redis, MQTT simulator not wired up, traffic not modelled): see
  `docs/SYNOPSIS_TRACEABILITY.md`.
- **Known limits and next steps:** `docs/HANDOFF.md`.

## Documentation

| File | Contents |
|---|---|
| `RUN_ON_YOUR_LAPTOP.md` | Install, run, tour, troubleshooting |
| `docs/SYNOPSIS_TRACEABILITY.md` | Each synopsis objective, workflow step and technology, mapped to code and evidence |
| `docs/CHANGELOG.md` | Every change made to the originally supplied project, and why |
| `docs/ARCHITECTURE.md` | System design |
| `docs/MDP.md`, `docs/ML.md`, `docs/CHARGER_SCORING.md`, `docs/SIMULATION.md` | The algorithms, with the bugs found in each |
| `docs/API.md` | Every endpoint |
| `docs/TESTING.md` | What is verified, what is not |
| `docs/VIVA_GUIDE.md` | Structured Q&A for the defence |
| `docs/HANDOFF.md` | Current state and what to do next |

## Repository layout

```
setup.sh / setup.bat    one-time setup          start.sh / start.bat    run everything
frontend/               Next.js app (app/, components/, charts/, services/, tests/), plus webapp/ (standalone demo)
backend/                FastAPI app: api/, services/, models/, schemas/, alembic/
optimization/           MDP, value iteration, reward and battery models, COS, fleet allocator
ml/                     forecasting models
simulation/             fleet simulator, baseline policies, experiment runner
tests/                  pytest suites, mirrored by module
docs/                   documentation
```
