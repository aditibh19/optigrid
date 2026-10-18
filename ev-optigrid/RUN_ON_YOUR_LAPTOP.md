# Run EV-OptiGrid on your laptop

You will end up with a website at **http://localhost:3000** (the app) talking to an API at
**http://localhost:8000** (the optimiser). Everything runs on your own machine. No accounts, API keys
or database server are needed.

## 1. Install two things (once)

| Tool | Version | Download | Check it worked |
|---|---|---|---|
| **Python** | **3.10, 3.11 or 3.12** (not 3.13) | https://www.python.org/downloads/ | `python --version` (Windows) or `python3 --version` (Mac/Linux) |
| **Node.js** | 18 or newer (20 or 22 LTS recommended) | https://nodejs.org/ | `node --version` |

- **Windows:** in the Python installer, tick **"Add python.exe to PATH"** before clicking Install.
- **Why not Python 3.13?** The project pins NumPy 1.26 and SciPy 1.13, which have no downloads for 3.13 yet, so
  installation fails halfway. If you already have 3.13, install 3.12 alongside it.
- You do **not** need PostgreSQL, Docker, Git or an internet connection after setup. (The street map needs internet;
  there is an offline "Schematic" map for when you don't have it.)

## 2. Set up (once, about 3 to 6 minutes)

Unzip the project, then open a terminal **inside the `ev-optigrid` folder**.

**Windows:** double-click `setup.bat` (or run `setup.bat` in Command Prompt).
**macOS / Linux:** run

```bash
./setup.sh
```

If it says "permission denied": `chmod +x setup.sh start.sh` and run it again.

It checks your Python and Node versions, creates a private Python environment (`backend/.venv`), installs the
packages (about 500 MB, mostly scikit-learn and XGBoost), creates a local SQLite database, and installs the
frontend packages. When you see **"Setup complete"** you are done with this step for good.

## 3. Start the app (every time)

**Windows:** double-click `start.bat`. Two windows open (backend and frontend) and your browser opens.
**macOS / Linux:** run `./start.sh`, then open **http://localhost:3000**. Press `Ctrl+C` to stop both.

The first page load is slow (it compiles the page). That's normal in development mode.

## 4. What you should see

1. A sign-in page. Click **"Explore with a demo account"**, no email needed. (Or create your own account.)
2. The **Overview** page, with a **green dot and "Backend connected"** at the bottom of the left sidebar.
   A red dot means the backend isn't running; see Troubleshooting.
3. The first time you open a page that uses the optimiser it may take a few seconds while it solves and caches
   its policies. It is instant afterwards.

Extras: interactive API documentation at http://localhost:8000/docs.

## 5. A 10-minute tour (good for a demo or viva)

| # | Page | What to show and say |
|---|---|---|
| 1 | **Overview** | ML forecasts of price, grid load, solar and queue. Each is labelled "Model forecast", never passed off as live data. |
| 2 | **Smart charging** | Press *Get recommendation*: charge now or wait, with reasons. Then use **"When conditions change"**: click *Price jumps 50%* and watch it detect the change and re-plan (before and after). This is the synopsis's re-optimisation loop. |
| 3 | **Journey planner** | Add a vehicle, plan Delhi to Agra: energy needed, whether you can arrive, stations on the way, on a map. |
| 4 | **Charging stations** | Stations ranked by the Charging Opportunity Score. Change the profile (Save money / Fastest / Battery health / Green / Balanced) and the ranking changes. |
| 5 | **Copilot** | Type "I need to reach Agra by 6pm with 80% charge". The language layer only extracts parameters; the optimiser makes the decision. |
| 6 | **How it decides > State space** | What a state is (567 per time slot), the Markov chains for price, grid and solar, and why the battery level is interpolated. |
| 7 | **Policy heatmap** | The optimal policy as a table: battery level against time slot. |
| 8 | **Bellman equation** | The calculation redone action by action for one state, with the badge "Check passed: matches the solver". |
| 9 | **Monte Carlo** | Hundreds of random scenarios on the same conditions: the optimiser saves money, and the page states the trade-off (a lower final charge) instead of hiding it. |
| 10 | **Sensitivity** | Raise the price or grid load and the recommended power falls, as it should. |
| 11 | **Digital twin** | Press Play: the optimised car and a charge-immediately car face identical prices, second by second. |
| 12 | **Policy simulator** | Five charging policies compared over a fleet, with confidence intervals. |
| 13 | **Fleet dashboard** | Urgent vehicles get power first; no charger or grid limit is ever exceeded. |
| 14 | **Battery health** | What wears a battery: speed, time nearly full, depth of swing, temperature. |

## 6. Run the tests

```bash
# backend + optimiser + ML + simulation (289 tests)
backend/.venv/bin/python -m pytest            # Windows: backend\.venv\Scripts\python -m pytest

# frontend unit tests (23 tests)
cd frontend && npm test

# live end-to-end check of the whole stack (start the app first)
cd frontend && npm run e2e
```

## 7. If you prefer to do it by hand

```bash
# terminal 1: backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                       # Windows: copy .env.example .env
python scripts/init_db.py
uvicorn main:app --reload

# terminal 2: frontend
cd frontend
npm install
npm run dev
```

## 8. Troubleshooting

| Problem | Cause and fix |
|---|---|
| Setup says **"needs Python 3.10, 3.11 or 3.12"**, or `pip` fails building NumPy/SciPy | You have Python 3.13 or newer. Install Python 3.12, then on Mac/Linux `PYTHON=python3.12 ./setup.sh`. Delete `backend/.venv` first. |
| **Red dot, "Backend offline"** | The backend window was closed or crashed. Start it again (`start.bat` / `./start.sh`) and read its window for the error. |
| `Address already in use` (port 8000 or 3000) | Another program (or an earlier copy of this one) is using it. Close it, or run the frontend on another port: `npm run dev -- -p 3001` and open that address. |
| The street map is grey or empty | You're offline (map tiles come from OpenStreetMap). Click **Schematic** above the map: it needs no internet. |
| **macOS:** XGBoost warning about `libomp` | Harmless. The app falls back to scikit-learn's gradient boosting. To use XGBoost: `brew install libomp`. |
| First simulator, heatmap or twin run is slow | It is solving and caching optimiser policies. Repeat runs are near-instant. The simulator refuses runs over 1,500 calculations (cars x repetitions x time slots) and tells you why. |
| "Session expired" / sent back to sign-in | Access tokens last 30 minutes and refresh silently for 7 days; if the backend's database was reset, sign in again. |
| Want a clean slate | Stop the app, delete `backend/evoptigrid.db` and everything in `optimization/artifacts/`, then run `python scripts/init_db.py` in `backend`. |
| **Windows:** `npm` blocked by "running scripts is disabled" | Use **Command Prompt** (cmd) instead of PowerShell, or run the batch files by double-clicking. |
| Want PostgreSQL instead of SQLite | Create a database, set `DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/dbname` in `backend/.env`, then in `backend`: `alembic revision --autogenerate -m "initial" && alembic upgrade head`. (Not yet tested by the authors; see docs/HANDOFF.md.) |

## 9. What is and is not verified

Everything above is checked by automated tests and a live end-to-end run against the real servers. Two things have
**not** been checked by anyone but you: how the pages *look* in a real browser (no browser was available while
building it), and the Windows `.bat` scripts (built on Linux). If a page looks wrong or a script misbehaves, that
is where to look first. See `docs/TESTING.md` and `docs/HANDOFF.md` for the full, honest list.
