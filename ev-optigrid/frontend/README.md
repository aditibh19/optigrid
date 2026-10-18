# EV-OptiGrid frontend (Next.js 14 + TypeScript)

A real Next.js App Router app that talks to the FastAPI backend. Every page
calls a live endpoint (see `docs/API.md`); nothing here is mocked.

## Run it

Easiest: from the project root run `setup.bat` / `./setup.sh` once, then `start.bat` / `./start.sh` (see `RUN_ON_YOUR_LAPTOP.md`).
By hand:

```bash
# 1. backend (terminal 1)
cd backend && pip install -r requirements.txt
cp .env.example .env && python scripts/init_db.py
uvicorn main:app --reload            # http://localhost:8000

# 2. frontend (terminal 2)
cd frontend && npm install
npm run dev                          # http://localhost:3000
```

The browser only talks to the Next.js server. `next.config.mjs` proxies `/api/*` to the backend (`BACKEND_URL`, default
`http://localhost:8000`), so no CORS setup is needed. Everything except `/login` needs a session; "Explore with a demo account" creates one.

## Pages

| Route | What it does |
|---|---|
| `/login` | Sign in, create an account, or use a demo account |
| `/` | Forecast tiles: price, grid load, solar, queue wait |
| `/smart-charging` | Charge-now-or-wait verdict with reasons, and **"When conditions change"** (monitor and re-optimise with before/after) |
| `/journey` | Vehicles, trip feasibility, stations along the route, map |
| `/stations` | Stations ranked by Charging Opportunity Score, on a map |
| `/copilot` | Plain-language request to target charge and deadline |
| `/fleet` | Allocate limited charger and grid power across vehicles by urgency |
| `/twin` | Digital twin: two cars, one scenario, played slot by slot |
| `/simulator` | Five charging policies compared over a simulated fleet |
| `/battery` | What wears a battery: speed, time nearly full, swing, temperature |
| `/optimiser/state-space` | What a state is; the Markov chains; battery-level interpolation |
| `/optimiser/policy` | The optimal policy as a heatmap |
| `/optimiser/bellman` | The Bellman equation, recomputed and checked against the solver |
| `/optimiser/monte-carlo` | Distributions over random scenarios, paired policy comparison |
| `/optimiser/sensitivity` | One-at-a-time sweeps of the inputs |

Every number shows its data source (live / demo / model forecast / simulated).

## Layout

```
app/           routes (one folder per page) + globals.css (design tokens)
components/    Shell (route guard, sidebar), AuthProvider, MapPanel / LeafletMap / MapView, TwinLane, MonitorPanel, PolicyControls, ui.tsx
charts/        Heatmap, LineChart, Histogram, MetricBars
services/      api.ts (typed client with silent token refresh), auth.ts (token storage), defaults.ts
hooks/         useVehicles, useRun
tests/         Vitest unit tests (api client, charts, map)
scripts/       e2e-live.ts (see below)
webapp/        the earlier standalone HTML/JS demo (kept; it does not call the backend)
```

## Checks

```bash
npm run typecheck      # tsc --noEmit
npm test               # 23 Vitest unit tests
npm run build          # production build (16 routes)
npm run e2e            # 36 live checks; needs backend + `npm run dev`/`start` running
```

`npm run e2e` runs the real `services/api.ts` against the live stack through the proxy. It is not a substitute for opening the
pages in a browser and clicking around, which no assistant has done.

## Not built / not verified

Tailwind CSS (the synopsis lists it; this UI uses a hand-written CSS design system), MQTT wiring, and any visual verification
in a real browser. `npm audit` reports Next.js 14.x advisories that only Next 16 fixes (a breaking upgrade needing React 19).
See `docs/HANDOFF.md`.

## Known behaviour

- The first simulator run on a fresh machine is slow (the optimiser solves and
  caches many policies). The page shows an estimate first and refuses setups
  above the backend's limit (`SIM_MAX_WORK`, default 1500 calculations).
- The demo vehicle id is kept in `localStorage`; if the backend database is
  reset, the journey page detects the stale id and asks you to save the
  vehicle again.
