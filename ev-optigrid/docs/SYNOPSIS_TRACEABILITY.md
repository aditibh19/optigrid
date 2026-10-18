# Synopsis traceability

How each item in the project synopsis ("EV-OptiGrid: An AI-Powered Personalized EV Charging, Route and Energy
Optimization System", JIIT) maps onto the code, where to see it running, and how it is checked. Where the
implementation differs from the synopsis, it says so.

Legend: **Done** = built and tested. **Partial** = built with a stated limit. **Not built** = not in the project.

## Objectives

| # | Synopsis objective | Status | Where it is | See it | Evidence |
|---|---|---|---|---|---|
| 1 | Intelligent charging recommendation (station + strategy) | Done | `optimization/`, `backend/services/optimization_service.py` | Smart charging, Charging stations | `tests/optimization/*`, `test_optimization_service.py`, e2e |
| 2 | Consider many factors at once (SOC, capacity, distance, price, power, wait, traffic, grid, renewables, battery health) | **Partial** | State = battery, price, grid load, solar; cost adds battery wear; COS adds distance, power, queue, price | Bellman equation, Stations | Traffic is **not** modelled: `journey_service` accepts a `traffic_multiplier` (default 1.0) but no source supplies it. |
| 3 | Stochastic Dynamic Programming | Done | `optimization/value_iteration.py`, `mdp.py`, `transition_model.py`, `reward_model.py` | State space, Policy heatmap, Bellman equation | Bellman page checks its arithmetic against the solver; `test_value_iteration.py`; 3 bugs found and fixed (docs/MDP.md) |
| 4 | ML for price, demand, queue, grid, renewables, trip energy | Done, on synthetic data | `ml/` (price, grid, solar, queue, demand) | Overview | `tests/ml/`, real held-out MAE/RMSE/R2 (docs/ML.md). Data is **synthetic and labelled so**. Trip energy shown to users is a physics formula; `demand_predictor` is trained to recover it. |
| 5 | Charging Opportunity Score (COS) | Done | `optimization/station_optimizer.py` | Charging stations | `test_station_optimizer.py`, docs/CHARGER_SCORING.md |
| 6 | Profiles: Save Money, Fastest, Battery Health, Green, Balanced | Done | `PROFILE_WEIGHTS` in `reward_model.py` | Profile selector everywhere; Sensitivity > profile | e2e runs all five |
| 7 | Battery-health-aware charging | Done | `optimization/battery_model.py` (wear enters the SDP cost) | Battery health | `test_battery_model.py`; the model is illustrative, **not** calibrated to real degradation data |
| 8 | Real-time re-optimisation | Done | `backend/services/monitor_service.py`, `POST /api/charging/monitor`, `MonitorPanel` | Smart charging > "When conditions change" | 9 monitor tests + e2e. Change detection runs when the client checks (button or 20 s watch), not as a server-side timer. |
| 9 | AI Charging Copilot (natural language, explained) | Done, rule-based | `backend/services/copilot_service.py` | Copilot | 23 tests. Extraction is a rule-based parser by default; a real LLM can replace only that step. The optimiser, never the language layer, decides. |
| 10 | What-If simulation: greedy, fixed, threshold, SDP | Done | `simulation/` (+ priority policy), Digital twin, Monte Carlo | Policy simulator, Digital twin, Monte Carlo | `test_fleet_simulator.py`, 18 tests; Monte Carlo compares policies on paired scenarios |
| 11 | Experimental evaluation metrics | Done | simulator output: cost, waiting, deadline and SOC violations, battery wear, renewable and charger utilisation | Policy simulator | e2e + tests |
| 12 | Scalable, fleet-ready | Partial | `optimization/multi_ev_optimizer.py`, `POST /api/fleet/allocate` | Fleet dashboard | Greedy allocator: constraint-safe, **not** globally optimal. The full SDP simulator is limited to ~1,500 calculations per run (docs/SIMULATION.md). |

## Workflow (synopsis section "Workflow")

| Step | Where |
|---|---|
| User registration and vehicle setup | Sign-in page (JWT + bcrypt), Journey planner > vehicle form |
| Journey input | Journey planner |
| Preference selection | Profile selector |
| Route and energy estimation | `POST /api/journeys` (demo routing provider by default) |
| Charging station discovery | Charging stations, route stations on the Journey page |
| Charging data collection | Station cards: price, power, expected wait, source label |
| Future condition prediction | Overview, `/api/predictions/*` |
| COS calculation | Charging stations |
| SDP optimisation and best plan | Smart charging |
| Personalised recommendation and explanation | Smart charging (verdict and reasons) |
| Charging execution / simulation | Digital twin |
| Real-time monitoring and re-optimisation | Smart charging > "When conditions change" |
| Performance analysis | Policy simulator, Monte Carlo |

## Technology stack (synopsis table) vs what is built

| Synopsis | Built | Note |
|---|---|---|
| Next.js, TypeScript | Yes (Next 14.2.35, App Router) | |
| **Tailwind CSS** | **No** | The UI uses a hand-written CSS design system (design tokens in `frontend/app/globals.css`). This is a deviation from the synopsis. |
| Leaflet / MapLibre | Yes, Leaflet | Street map (OpenStreetMap tiles) with an offline schematic fallback. Not visually verified in a browser. |
| Python, FastAPI | Yes | 33 API endpoints |
| PostgreSQL | Supported, **untested** | Default is SQLite so it runs on any laptop. Set `DATABASE_URL` for PostgreSQL. |
| SQLAlchemy, Alembic | Yes | No migration files are shipped: generate with `alembic revision --autogenerate`. |
| NumPy, SciPy | NumPy yes | The optimiser is NumPy-only. SciPy is installed as scikit-learn's dependency; the project's own code does not import it. |
| Value iteration | Yes | |
| Scikit-learn, XGBoost | Yes | XGBoost is used when its native library loads, otherwise scikit-learn gradient boosting (and the app says so). |
| Pandas | Yes | |
| JWT, bcrypt | Yes | Access + refresh tokens, owner-only data, refresh-token rejection as access, startup guard against the default secret in production |
| Redis / in-memory LRU | **In-memory LRU** (plus a disk cache) | No Redis. |
| FastAPI BackgroundTasks, APScheduler | APScheduler | Warms the ML models at startup and hourly. Re-optimisation monitoring is client-triggered. |
| MQTT, ESP32 simulator (optional) | Simulator module only | `backend/services/iot_telemetry.py` exists; it is not connected to the API or UI. |
| Pytest, Vitest/Jest | Yes, both | 289 pytest + 23 Vitest + 36 live e2e checks |
| Git, GitHub | n/a | Not part of the delivered files. |

## Known limits worth stating in a viva

- All ML training data and all "live" providers are synthetic or demo unless real API keys are configured; every response says which (`source`).
- The SDP discretises battery level in 5-point steps and price, grid load and solar into three levels each. That is what makes an exact solution possible; the cost is coarse conditions.
- Under the "balanced" profile the optimiser saves money by accepting a lower final charge in many scenarios. The Monte Carlo page reports this openly.
- Prices, grid load and solar are modelled as independent Markov chains with hand-set persistence, not fitted to real data.
