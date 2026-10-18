# API Reference

Base URL: `http://localhost:8000`. Interactive OpenAPI docs at `/docs` once
the server is running (`uvicorn main:app --reload` from `backend/`).

## Auth (`/api/auth`)

> **Authentication.** Send `Authorization: Bearer <access token>` on every endpoint except `/health*`, `/api/auth/*`,
> `/api/predictions/*` and `/api/stations/*` (public market data). Access tokens last 30 minutes; a refresh token (7 days)
> exchanges for a new pair. A refresh token is rejected when used as an access token. Vehicles, journeys and optimisation
> results are **owner-only**: another user's ids return **404** (not 403), so ids can't be probed. Anonymous calls return **401**.
> In any non-development `ENVIRONMENT` the server refuses to start with the built-in default `JWT_SECRET_KEY`.

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/register` | `{email, password, name}` | Returns access + refresh JWT |
| POST | `/login` | `{email, password}` | Returns access + refresh JWT |
| POST | `/refresh` | `{refresh_token}` | New access + refresh pair |
| GET | `/me` | | `{id, email, name}` of the logged-in user |

## Vehicles (`/api/vehicles`)
| Method | Path | Notes |
|---|---|---|
| POST | `` | Create a vehicle for the logged-in user (a `user_id` in the body must be your own, else 403) |
| GET | `` | List the logged-in user's vehicles (`?user_id=` is accepted only if it is your own, else 403) |
| GET | `/{vehicle_id}` | Get one vehicle |

## Journeys (`/api/journeys`)
| Method | Path | Notes |
|---|---|---|
| POST | `` | Plans a route, computes energy requirement (Phase 11), persists Journey + Route. Returns `journey_id` (needed by `/charging/reoptimize` and `/schedule`). 404 if `vehicle_id` is unknown |

## Stations (`/api/stations`)
| Method | Path | Notes |
|---|---|---|
| GET | `/nearby?lat=&lng=&radius_km=&profile=` | COS-ranked nearby stations, tagged `source` |
| GET | `/route?origin_lat=&origin_lng=&dest_lat=&dest_lng=` | Stations along a route |

## Charging (`/api/charging`)
| Method | Path | Notes |
|---|---|---|
| POST | `/optimize` | Runs the SDP, returns recommendation + explanation. Works standalone (no journey); returns `result_id` for `/explanation`. 422 on unknown `profile` |
| POST | `/reoptimize?journey_id=` | Marks the previous result stale, creates a new run |
| GET | `/schedule?journey_id=` | Latest non-stale result for a journey (includes `result_id`) |
| GET | `/explanation?result_id=` | Structured reasons for a result |

### `POST /api/charging/optimize` request body
```json
{
  "battery_capacity_kwh": 60.0,
  "max_charge_rate_kw": 50.0,
  "current_soc_pct": 32.0,
  "target_soc_pct": 90.0,
  "minimum_safe_soc_pct": 70.0,
  "horizon_slots": 24,
  "slot_minutes": 15,
  "current_price_per_kwh": 8.0,
  "current_grid_load_pct": 60.0,
  "current_solar_availability_frac": 0.2,
  "profile": "balanced"
}
```
Response mirrors `OptimizeChargingResponseSchema` (`backend/schemas/charging.py`):
`result_id`, `recommended_action`, `action_kw`, `is_feasible`,
`max_achievable_soc_pct`, `estimated_cost`, `immediate_cost`,
`explanation_paragraph`, `reasons[]`.

> **Reading the cost fields:** `estimated_cost` is the cost of *this slot's
> action* (`action_kw × price × slot_hours`) and `immediate_cost` is one slot
> at full power — both are **per-slot**, not the total cost of the whole
> charge. A `wait` recommendation therefore shows `estimated_cost: 0.0`.
> Don't present these to end users as "session cost" without relabelling.

## Predictions (`/api/predictions`)
| Method | Path | Notes |
|---|---|---|
| GET | `/prices` | Price forecast (trains on first call if no saved model) |
| GET | `/grid` | Grid load forecast |
| GET | `/solar` | Solar generation forecast |
| GET | `/queue` | Station queue/wait forecast |

## Simulation (`/api/simulation`)
| Method | Path | Notes |
|---|---|---|
| GET | `/limits` | `max_work` (default 1500, env `SIM_MAX_WORK`) and the cost formula, so clients can show an estimate |
| POST | `/run` | Runs the 5-algorithm comparison across N replications, persists an Experiment. Defaults: 10 cars, 2 repetitions, 24 slots. **422** if `num_evs × n_replications × horizon_slots` exceeds `max_work` (only when the SDP is included) |
| GET | `/results?experiment_id=` | Retrieves a past experiment's results |

> **Cost:** the SDP policy is solved per car per time slot, and the policy cache
> rarely hits for a mixed fleet, so a first run costs about 16 solves/second
> (~18 s for the defaults; repeats are near-instant). Larger runs are refused
> up front rather than timing out.

## Copilot (`/api/copilot`)
| Method | Path | Notes |
|---|---|---|
| POST | `/parse` | Extracts intent/params, validates, calls the optimizer, returns a reply |

## Monitoring and re-optimisation (`/api/charging`)
| Method | Path | Notes |
|---|---|---|
| GET | `/monitor/thresholds` | How large a change must be before a plan is recomputed: price 15%, grid 10 points, solar 0.2, queue 10 min, deadline 15 min, target 5 points |
| POST | `/monitor` | Body `{previous, current, previous_queue_wait_min?, current_queue_wait_min?, journey_id?}` (`previous`/`current` are optimize request bodies). Returns `{changed, triggers[], action_changed, previous, current}`. If something material changed, a new plan is **stored** (against the journey when given, marking the old one stale). Otherwise nothing is stored. |

## How the optimiser decides (`/api/analysis`, login required)
| Method | Path | Notes |
|---|---|---|
| GET | `/state-space` | Levels, thresholds, action set, state counts, the three Markov transition matrices |
| GET | `/soc-transition?soc_pct&action_kw&battery_capacity_kwh&slot_minutes` | How the battery level moves between buckets (linear interpolation), with the nearest-bucket alternative for comparison |
| POST | `/policy-heatmap` | Optimal action and value over battery level by time slot, or by price / grid / solar level |
| POST | `/bellman` | The Bellman backup for one state, action by action (cost components, discounted future value, Q). Returns `matches_solver`, checking its own arithmetic against the solver's value function and action |
| POST | `/monte-carlo` | `n_runs` (10 to 2000) random scenarios; three policies on identical paths; distributions, paired savings with a 95% CI. `n_runs x horizon_slots` is limited to 60,000 (422 otherwise) |
| POST | `/sensitivity` | Sweep `soc`, `price`, `grid`, `solar`, `profile` or `cost_weight`; returns the recommended power and value for each point |

All take the policy parameters (`battery_capacity_kwh`, `max_charge_rate_kw`, `target_soc_pct`, `minimum_safe_soc_pct`,
`horizon_slots` 2 to 96, `slot_minutes`, `profile`); most also take the current conditions.

## Digital twin, fleet, battery (login required)
| Method | Path | Notes |
|---|---|---|
| POST | `/api/twin/run` | One simulated session, slot by slot, for the optimised policy and for charge-immediately on the same price / grid / solar path (`seed` selects the scenario) |
| POST | `/api/fleet/allocate` | Vehicles (SOC, target, battery, max kW, urgency 1 to 5, hours to ready), chargers and a grid limit. Each charger is a power pool that can serve several vehicles; every vehicle uses one charger. Returns per-vehicle allocation, charger loads, constraint violations (always empty) and the service score against first-come-first-served |
| GET | `/api/battery/curves?max_charge_rate_kw&ambient_temp_c` | Wear against charging speed, end charge and temperature, split into its four components, plus the health indicator curve |

## Every response's data-source labeling

Any field describing a route, station, price, grid, or solar value carries
(directly or via its parent object) a `source` of `real`, `simulated`,
`predicted`, or `demo` — never omitted (spec §29). Consult
`docs/LOCATION_SERVICES.md` and `docs/ML.md` for what each label means in
context.
