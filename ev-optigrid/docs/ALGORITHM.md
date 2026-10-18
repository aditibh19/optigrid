# Algorithms — Overview

This is the map of every algorithmic component and where it lives. Each
has its own deeper doc; this page is the index plus how they connect.

## The pipeline, end to end

```
1. Journey energy model          services/journey_service.py           (this page, "Journey energy")
2. Station discovery              services/providers/*                 (docs/LOCATION_SERVICES.md)
3. Per-station forecasts          ml/price_forecaster.py, grid_*, solar_*, queue_predictor.py  (docs/ML.md)
4. Charging Opportunity Score      optimization/station_optimizer.py     (docs/CHARGER_SCORING.md)
5. Feasibility check               optimization/value_iteration.py       (docs/MDP.md)
6. SDP policy lookup/solve         optimization/policy.py, value_iteration.py (docs/MDP.md)
7. Multi-objective cost             optimization/reward_model.py          (docs/MDP.md)
8. Explanation generation          optimization/explainability.py        (this page, "Explainability")
9. Persistence                     backend/models/optimization.py        (docs/DATABASE.md)
```

Re-optimization re-enters at step 3/6; nothing above it needs to re-run
unless the trigger specifically invalidates it (e.g. a station going
offline only affects step 4 onward, not the SDP solve).

## Journey energy model (Phase 11, spec §5)

`services/journey_service.py::estimate_journey_energy` — pure physics:

```
energy_required_kwh = distance_km * efficiency_kwh_per_km * traffic_multiplier
                     + elevation_gain_m * elevation_cost_kwh_per_m
expected_arrival_soc = current_soc - (energy_required_kwh / battery_capacity_kwh) * 100
minimum_safe_soc = 15% of the trip's own energy requirement, as a SOC percentage
```

`is_feasible_without_charging = expected_arrival_soc >= minimum_safe_soc`.
If not, `required_charge_before_departure` computes exactly how much SOC
(percentage points) closing the gap needs.

`ml/demand_predictor.py` offers a learned alternative to the first line
once real trip data exists; both are intentionally kept independent so one
can sanity-check the other.

## Charging Opportunity Score (Phase 9)

Covered fully in `docs/CHARGER_SCORING.md`. One-line summary: min-max
normalize every raw attribute across the current candidate stations, weight
by the active profile, sum, scale to 0-100.

## Stochastic Dynamic Programming (Phase 4/5) - the core academic component

Covered fully in `docs/MDP.md`. One-line summary: finite-horizon backward
induction over a discretized (SOC x price x grid x solar) state space,
with linear-interpolated SOC transitions (to avoid a discretization
self-loop bug - see MDP.md) and a per-slot multi-objective cost.

## Explainability (Phase 18, spec §18)

`optimization/explainability.py::build_explanation` takes a
`DecisionContext` built from the SAME variables the optimizer just used
(current/predicted price, grid, solar, feasibility, costs) and returns a
list of `(reason_code, reason_text, supporting_value)` - never inventing a
number that wasn't already computed elsewhere. Priority order: infeasibility
first (the user needs to know the target itself changed before anything
about timing), then price/grid/renewable advantages, then feasibility
confirmation, then battery/cost framing. Always returns at least one reason
(falls back to a plain price/grid statement).

## Baseline policies + fleet simulation (Phase 6/7, spec §15)

`simulation/baseline_policies.py` implements Greedy, Fixed Schedule, Price
Threshold, and Priority as per-vehicle "desired power" functions;
`simulation/fleet_simulator.py` arbitrates real contention (limited
chargers/grid capacity) and computes the full metric set spec §15 asks for
(cost, peak load, waiting, SOC/deadline violations, degradation, renewable
utilization, charger utilization, energy purchased).
`simulation/experiment_runner.py` runs every algorithm across repeated
seeds and reports mean/std/95% CI, never hardcoded (spec §42).

Measured result: SDP beats Greedy by roughly 28% on cost and roughly 2.5x
on renewable utilization, at the cost of somewhat more deadline violations
under heavy charger contention - a genuine efficiency-vs-reliability
trade-off, not a one-sided win.

## Multi-EV joint allocator (Phase 17, spec §16)

`optimization/multi_ev_optimizer.py::allocate_fleet_charging` - a
value-density-ranked (urgency-weighted benefit per kW, not just raw
urgency) greedy allocator that assigns each vehicle to at most one charger
and splits power fractionally, with vehicle/charger/grid capacity limits
enforced by construction rather than hoped for. `validate_allocation`
checks all three constraint types explicitly.

## AI Copilot extraction (Phase 15, spec §14)

`backend/services/copilot_service.py`. Rule-based (regex/keyword) parameter
extraction stands in for the LLM extraction step in this build (works with
zero API keys) - followed by mandatory schema validation
(`validate_parameters`) before anything reaches the optimizer. The
orchestration function (`handle_message`) takes the optimizer as an
injected callback and never fabricates a `recommended_action` itself.
