# Simulation

Two related but distinct simulation layers exist in this project — worth
distinguishing clearly in a viva.

## 1. Python backend simulation (exact, spec §15/§16/§31)

`simulation/fleet_simulator.py` runs the REAL per-vehicle policies
(including the actual SDP via `optimization/policy.py`) inside a fleet with
constrained chargers and grid capacity. This is what
`simulation/experiment_runner.py` uses to produce the mean/std/95% CI
numbers for the Research Dashboard, and what `/api/simulation/run` exposes.
Cost model (measured): each SDP decision needs a policy for that car's own
battery, charge rate, target **and remaining horizon**, and that key changes
every time slot, so in a mixed fleet the cache rarely hits *within* a first
run. A first run therefore costs about `cars × repetitions × time slots`
solves at ~16 solves/s (10 cars × 2 reps × 24 slots ≈ 18 s cold, 0.4 s when
repeated). A 25 × 5 × 48 run needs ~6,000 solves (>5 min, ~200 MB of cache),
so `/api/simulation/run` refuses setups over `SIM_MAX_WORK` (default 1500).
Making large fleets practical needs a coarser cache key (bucketed battery /
rate / horizon) or a background job with progress — see `docs/HANDOFF.md`.
(An earlier version of this file claimed it "scales to hundreds of vehicles
because policy solves are cached"; that was wrong for heterogeneous fleets.)

Run it directly:
```bash
python -c "
from simulation.fleet_simulator import FleetSimulationConfig, run_fleet_simulation
config = FleetSimulationConfig(num_evs=25, num_chargers=6, charger_power_kw=50.0, grid_capacity_kw=250.0, horizon_slots=48, seed=1)
for algo in ('greedy','fixed_schedule','price_threshold','priority','sdp'):
    print(algo, run_fleet_simulation(config, algorithm=algo))
"
```

## 2. Frontend fleet-scale proxy (fast, illustrative)

The standalone frontend demo (`frontend/webapp/`) needs to stay responsive
in-browser, and running hundreds of independent value-iteration solves in
JavaScript (no NumPy-equivalent vectorization) is measurably too slow for
an interactive "move a slider, see it update" experience — a single solve
takes roughly 50-130ms even in Node, and a naive port doesn't batch across
vehicles the way the Python backend's caching does.

So the What-If Simulator and Analytics pages in the frontend use a fast,
clearly-labeled heuristic proxy (`app.js::runAlgorithmComparison` and the
`sim-run` handler) that reproduces the *qualitative* pattern the real
simulator shows (SDP: lower cost, higher renewable use, somewhat more
contention-driven violations) without solving the real optimization
per vehicle. This is disclosed directly in the UI's own caption text, not
hidden — spec §42's "don't fake calculations" principle is satisfied by
being honest about which layer is exact and which is an illustrative
proxy, rather than by pretending the fast path is the real thing.

The **Smart Charging** and **Journey Planner** pages, by contrast, DO run
the exact ported SDP/journey-energy engine (`engine.js`) for the single
active vehicle — that scale (one vehicle, a handful of re-optimizations) is
well within interactive budget (tested at ~50ms per solve, cached
thereafter).

## Reproducibility

Both layers use seeded random number generators (`numpy.random.default_rng`
in Python, a linear-congruential `seededRandom` in JS) — the same seed
always produces the same synthetic fleet/exogenous sequence, which is what
makes `experiment_runner.py`'s repeated-replication statistics meaningful
(each replication uses `base_seed + rep_index`, not fresh entropy each
time).
