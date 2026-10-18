# HANDOFF: read this first

For a new Claude session or a human picking the project up. Read this, then `docs/TESTING.md` and `docs/SYNOPSIS_TRACEABILITY.md`.

## What this is

EV-OptiGrid (JIIT major project): a personalised EV charging decision-support system. Stochastic dynamic programming (value
iteration) decides when, where, how much and how fast to charge, with ML forecasts, a station score (COS), battery-wear
awareness, a fleet allocator, a simulator, a copilot and a Next.js frontend. Run it with `RUN_ON_YOUR_LAPTOP.md`.

## History (explains the gaps)

1. **Original project (supplied):** algorithms, ML, simulation and a backend written in a sandbox with no network; the backend was
   only syntax-checked and there was no working Next.js frontend.
2. **Backend session:** ran everything for real; found and fixed 9 bugs (bcrypt, missing dependency, UUIDs on SQLite, nullable
   column, station fallback, missing ids, unknown vehicle, policy-cache corruption, simulator cost). 
3. **Frontend + completion session:** built the Next.js app; enforced authentication; built the analysis pages, digital twin, fleet,
   battery, map and monitoring loop; added APScheduler, an in-memory LRU cache, Vitest tests and one-command setup scripts.
   Found ten more issues (see `docs/TESTING.md` bugs 10 to 19). Every change is listed in `docs/CHANGELOG.md`.

## Status

- **289 backend tests, 23 frontend tests, 36 live end-to-end checks: all passing.**
- 33 API endpoints; 15 frontend pages plus login; production build clean.
- Run: `setup.sh|bat` once, `start.sh|bat` after; open http://localhost:3000.

## NOT verified. Do these first

1. **Open every page in a real browser** (Chrome or Edge). Nobody has seen the pages rendered: layout, colours, spacing, the animated
   digital twin, responsiveness, keyboard focus are all untested visually. Fix whatever looks off.
2. **The Leaflet street map** (needs internet; the schematic fallback works offline).
3. **The Windows scripts** `setup.bat` / `start.bat` (built on Linux, syntax-reviewed only).
4. **PostgreSQL.** SQLite is the default and the only thing tested. Models use a native UUID on Postgres, never executed.
5. Real providers (Mapbox / OSRM / OpenChargeMap / OpenWeather / Anthropic): only the `demo` stack has been run.

## Known issues and design limits

1. **`npm audit`:** Next.js 14.x advisories are only fixed in Next 16 (breaking: React 19). Pinned at 14.2.35. Fine for local use; upgrade
   before exposing to the internet.
2. **Tokens live in `localStorage`** (XSS-readable). Production should use an httpOnly, SameSite cookie for the refresh token.
3. **No rate limiting.** `rate_limit_per_minute` exists in settings but is not enforced. Heavy endpoints (simulator, Monte Carlo)
   have work limits and need login, but there is no per-user throttle.
4. **Simulator cost:** ~cars x repetitions x slots policy solves at ~16/s; runs over `SIM_MAX_WORK` (1500) are refused (422). Making big
   fleets practical needs a coarser cache key or background jobs. See `docs/SIMULATION.md`.
5. **Policy cache growth:** `optimization/artifacts/*.npz` is regenerable and git-ignored; unique parameter combinations each add a
   file, so it can grow. Delete freely. An in-memory LRU (`POLICY_MEMORY_CACHE_SIZE`, default 128) sits in front of it.
6. **Cost fields are per-slot.** `estimated_cost` / `immediate_cost` are the cost of the next slot's action, not the whole charge.
7. **Optimiser behaviour:** under "balanced" it often ends below the target charge to save money (Monte Carlo page shows the rate).
   That is the objective working as written; choose "Fastest" or a longer look-ahead to change it.
8. **Monitoring is client-triggered** (button or 20 s watch), not a server-side timer. APScheduler currently only warms the ML models.
9. **Modelling simplifications:** price / grid / solar are independent Markov chains with hand-set persistence; battery level in
   5-point buckets; wear model illustrative; traffic not modelled; ML data synthetic. See `docs/SYNOPSIS_TRACEABILITY.md`.
10. No Alembic migration files are shipped (generate with `alembic revision --autogenerate`); `scripts/init_db.py` builds tables directly.
11. `bcrypt` is pinned to 4.0.1 on purpose (`passlib 1.7.4` breaks with newer bcrypt).

## Differences from the synopsis

Tailwind CSS not used (custom CSS design system); no Redis (in-memory LRU + disk cache instead); MQTT/ESP32 simulator exists
(`backend/services/iot_telemetry.py`) but is not wired to the API or UI; SciPy is only an indirect dependency; PostgreSQL untested.

## Suggested next steps

1. Browser pass over all pages; fix visual issues.
2. Decide on Tailwind: either migrate (the design tokens in `frontend/app/globals.css` map straight onto a Tailwind theme) or keep
   and justify.
3. Try PostgreSQL and real providers with keys.
4. Upgrade to Next 16 / React 19 and re-run `npm run build`, `npm test`, `npm run e2e`.
5. Rate limiting; move the refresh token to an httpOnly cookie.
6. Wire the IoT simulator to a WebSocket and a live "charger telemetry" panel on the digital twin.
7. Keep `docs/TESTING.md` honest about verified versus not.

## File map

```
RUN_ON_YOUR_LAPTOP.md     install, run, 10-minute tour, troubleshooting
setup.sh|bat  start.sh|bat
docs/CHANGELOG.md         every change to the originally supplied project
docs/SYNOPSIS_TRACEABILITY.md   synopsis -> code -> evidence, and deviations
docs/ARCHITECTURE.md  MDP.md  ML.md  CHARGER_SCORING.md  SIMULATION.md  API.md  TESTING.md  SETUP.md  VIVA_GUIDE.md
frontend/README.md        the Next.js app
```
