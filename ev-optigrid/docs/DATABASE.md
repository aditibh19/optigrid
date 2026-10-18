# Database

PostgreSQL in production; SQLite is supported transparently for local dev
(`DATABASE_URL=sqlite:///./evoptigrid.db`) via SQLAlchemy's UUID/String
variant handling in every model.

## Design principles

1. **Every time-series / discoverable-data table carries a `source` column**
   (`DataSource`: `real | simulated | predicted | demo`). This is a hard
   project rule (spec §29): the UI must never present simulated data as if
   it were live. Tables: `routes`, `charging_stations`, `electricity_prices`,
   `grid_load`, `solar_generation`, `station_demand`, `charging_sessions`
   (via `session_type`).

2. **Optimization runs are append-only.** `optimization_runs` +
   `optimization_results` are never updated in place — a re-optimization
   (spec §12) always inserts a new run and a new result, with
   `superseded_by_run_id` linking the old result forward. This gives a full,
   auditable decision history and makes "old plan vs new plan" comparisons a
   simple query rather than a diffing problem.

3. **Explanations are structured, not generated text stored as fact.**
   `optimization_explanations` stores `(reason_code, reason_text,
   supporting_value)` rows produced directly from the optimizer's own
   variables. The AI Copilot is only allowed to *phrase* these rows in
   prose — never to invent new ones (spec §14, §18).

4. **Explicit user preferences vs. learned behaviour.** `user_preferences`
   holds only what the user has explicitly set. Any inferred/learned
   behaviour (e.g. "usually leaves at 7:30") is computed at query time from
   `journeys` history in the personalization service — it is intentionally
   NOT persisted as if it were an explicit preference, so it can never
   silently outrank an explicit instruction (spec §8).

5. **Custom optimization weights are nullable overrides.** `user_preferences`
   has one nullable `custom_w_*` column per multi-objective cost term (§7).
   They only take effect when `profile == CUSTOM`; otherwise the
   profile-derived default weight table in `optimization/reward_model.py` is
   used. This avoids duplicating the full weight vector for every profile.

## Entity groups

| Group | Tables |
|---|---|
| Identity | `users`, `user_preferences` |
| Vehicle | `vehicles` |
| Journey | `journeys`, `routes` |
| Infrastructure | `charging_stations`, `chargers` |
| Sessions | `charging_sessions` |
| Time-series | `electricity_prices`, `grid_load`, `solar_generation`, `station_demand` |
| ML | `predictions` |
| Decisions | `optimization_runs`, `optimization_results`, `optimization_explanations` |
| Ops | `notifications`, `audit_logs` |
| Research | `experiments`, `experiment_results` |
| Fleet | `fleet_vehicles` |

## Migrations

Schema is managed with Alembic (`backend/alembic/`). The models are the
source of truth (`backend/models/`); after any model change:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

For a disposable local database, `python backend/scripts/init_db.py` creates
all tables directly without migration history — useful for quick iteration,
not for tracking schema evolution.

## Indexing strategy

Composite indexes are placed on the columns every service actually filters
by: `(region, timestamp)` on all three time-series tables, `(station_id,
timestamp)` on `station_demand`, `(user_id, created_at)` on `journeys`,
`(type, target_time)` on `predictions`, and `(station_id, status)` on
`chargers` for fast "available chargers at station X" lookups feeding the
COS calculation.
