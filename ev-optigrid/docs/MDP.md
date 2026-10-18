# The Stochastic Dynamic Programming Engine

This is the core academic contribution of EV-OptiGrid (spec §6). This
document is written to be read out loud in a viva.

## 1. Why not just greedy or threshold charging?

A greedy policy ("charge now at max rate") ignores that electricity price,
grid load, and solar availability change over the hours before a deadline —
it can't express "it's worth waiting 40 minutes because price drops 40%
overnight". A fixed-threshold policy ("charge if price < X") ignores the
deadline entirely — it might wait forever if price never dips, and misses
the target. Both are implemented as baselines (`simulation/baseline_policies.py`)
specifically so the SDP's advantage over them is measurable, not asserted
(Research Dashboard, §31).

## 2. Why stochastic dynamic programming specifically?

The user doesn't know tomorrow's exact price or grid load — only a
distribution over how they're likely to evolve. SDP is the standard
framework for sequential decisions under this kind of uncertainty: it
doesn't commit to one guessed future, it optimizes against the *expected*
cost over all plausible futures, weighted by how likely each is.

## 3. Formulation choice: finite-horizon, not infinite-horizon

Most textbook presentations of the Bellman equation use an infinite
horizon with geometric discounting. We deliberately use a **finite-horizon**
formulation instead, because a charging decision problem bounded by a known
departure deadline *is* finite — there is a specific slot `T` after which
the decision no longer matters. Modeling it as infinite-horizon would
either ignore the deadline or require bolting "time remaining" on as an
extra state dimension purely to fake a horizon, which only adds
dimensionality for no benefit. Solving backward from `T` to `0` costs less computation.

## 4. State

```
s = (soc_bucket, price_bucket, grid_load_bucket, solar_bucket)
```

| Variable | Discretization |
|---|---|
| SOC | 0–100% in steps of 5 → 21 buckets |
| Electricity price | 3 buckets: low / medium / high |
| Grid load | 3 buckets: low / medium / high |
| Solar generation | 3 buckets: none / some / high |

Time-to-deadline is **not** a state dimension — it's the backward-induction
index `t` itself, which is more natural and keeps the state space at
21 × 3 × 3 × 3 = 567 states per time slot, small enough to solve exactly
(no function approximation needed) at request time.

Why buckets and not continuous values? A continuous-state Bellman equation
has no closed form here and would require a function approximator (e.g. a
neural net critic), which trades exactness for scale we don't need — 567
states solves in well under a second (measured: <150ms for a 12-slot
horizon across all 5 profiles combined, cached thereafter). If a future
version needs finer resolution, the bucket counts are the only thing that
changes (`optimization/mdp.py`).

## 5. Action

```
a ∈ {0, 5, 10, 15, 20, 25, 30, 40, 50} kW
```

configurable, and capped per-session at `min(vehicle.max_charge_rate_kw,
charger.power_kw)` (`MDPConfig.feasible_actions_kw`).

## 6. Transition model

SOC's transition given an action is **deterministic** (battery physics):

```
soc' = clamp(soc + (a * η_charge * Δt / battery_capacity_kwh) * 100)
```

Price, grid load, and solar generation each evolve as an independent
first-order Markov chain over their 3 buckets
(`optimization/transition_model.py`):

- `build_default_transition_matrix` — a documented-as-synthetic,
  persistence-parameterized matrix (mean-reverting: more likely to move to
  a neighboring bucket than to jump low→high in one slot) for when no
  historical data is available yet.
- `estimate_transition_matrix` — a smoothed maximum-likelihood estimate
  from an actual bucketized history, which is what a production deployment
  would use once `electricity_prices` / `grid_load` / `solar_generation`
  accumulate enough rows.

The independence assumption across price/grid/solar is a simplification —
documented, not hidden — made so the joint transition tensor stays a
tractable 3×3×3×3×3×3 (729-entry) array rather than requiring a jointly
estimated model.

## 7. Cost function and Bellman equation

Per-slot cost `C(s,a)` (implemented in `optimization/reward_model.py::step_cost`):

```
C(s,a) = w_cost * electricity_cost_norm(s,a)
       + w_battery * degradation_cost(s,a)
       + w_grid * grid_peak_penalty(s,a)
       - w_renewable * renewable_reward(s,a)
```

Terminal cost at `t = T` (`terminal_cost`):

```
C_T(s) = w_unmet * max(0, target_soc - soc)/100
       + w_deadline * max(0, min_safe_soc - soc)/100 * 5
```

Bellman recursion, solved backward from `t = T`:

```
V_T(s)   = C_T(s)
V_t(s)   = min_a [ C(s,a) + γ * Σ_s' P(s'|s,a) V_{t+1}(s') ]
π_t(s)   = argmin_a [ ... ]
```

`γ = 0.99` — a mild discount even within the finite horizon, so the
optimizer has a slight preference for resolving cost sooner rather than
later when two paths are otherwise equal (numerically stabilizing, not
load-bearing for the deadline behaviour, since the terminal cost already
enforces the deadline directly).

**Why `w_wait` and `w_travel` don't appear here:** those two weights from
the full 8-term multi-objective function (§7) apply at the *station
selection* level (how long you'll queue, how far you'll drive to get
there), not the *charging-rate* decision at a station you've already
picked. They're consumed by the Charging Opportunity Score
(`optimization/station_optimizer.py`, Phase 9) instead. See
`docs/CHARGER_SCORING.md`.

## 8. Normalization — a real bug we hit and fixed

Initially, `electricity_cost` was left in raw currency units (₹, tens to
hundreds per slot) while `unmet`/`deadline` penalties were expressed as
normalized SOC fractions (0–5ish). The optimizer always chose "never
charge" because the real-currency cost term dominated every other term
regardless of weight — the weights were mathematically present but
practically meaningless. Fixed by normalizing electricity cost against the
worst-case per-slot spend (`_WORST_CASE_PRICE` in `reward_model.py`) so all
terms live on a comparable scale before weights are applied. This is
exactly the normalization discipline described for the Charging
Opportunity Score in §4 — it turned out to matter just as much for the
reward function. `optimization/demo_sdp.py` is the regression check for
this: it fails loudly (`[WARN]`) if charging is never deferred/never
happens as expected.

## 9. Six user profiles, one cost function

Profiles (`optimization/reward_model.py::PROFILE_WEIGHTS`) are just
different weight vectors over the same `C(s,a)`. Switching profile does not
change any code path — it changes which action the argmin picks. Verified
empirically in `optimization/demo_sdp.py` Test 2: the same state (high
price, high grid load, 60% SOC, 2 slots from deadline) produces a different
recommended charging power for `save_money` (0 kW — wait, accept the
penalty) vs `battery_health`/`balanced` (10 kW — split the difference) —
proving the weights are load-bearing, not decorative.

## 10. Handling infeasibility (urgent mode, §13)

If the maximum-power policy still can't reach `target_soc` by the deadline
(too little time, too slow a charger), `V_0` reflects that — the value
function itself encodes "how short of target you'll end up even doing your
best". `services/optimization_service.py` (Phase 12) reads the resulting
achievable SOC and surfaces it directly rather than promising the original
target: *"90% is infeasible before departure; maximum achievable SOC is
X%."*  Verified in `optimization/demo_sdp.py` Test 4.

## 11. Caching (§36)

Solving is fast (~25ms per profile for a 12-slot horizon) but not free, and
identical requests (same vehicle spec, profile, target/min SOC) shouldn't
re-solve. `optimization/policy.py` hashes the solve inputs into a cache key
and persists `(V, policy)` arrays to `optimization/artifacts/*.npz`.
Measured: second call for an identical configuration returns in ~2ms vs
~136ms for the first (cold) solve.

## 12. Limitations (to state proactively in the viva)

- Price/grid/solar are assumed to transition independently of each other,
  which isn't strictly true (grid load and price are correlated in
  reality). A joint model would need either a larger joint transition
  tensor or a learned joint process; left as a documented simplification.
- 3-level bucketing of price/grid/solar is coarse. It was chosen to keep
  the state space small enough to solve exactly and instantly; a finer
  grid trades solve time for resolution and is a one-line config change
  (`optimization/mdp.py`) if the deployment needs it.
- The Markov transition matrices used by default are synthetic
  (persistence-parameterized), not fit to real historical data, until
  `estimate_transition_matrix` is wired to real `electricity_prices` /
  `grid_load` / `solar_generation` rows (Phase 8/10).

## 13. Three more real bugs, found via fleet simulation (Phase 6/7)

Running the SDP inside a multi-vehicle fleet simulation (spec §15) surfaced
three additional bugs that a single-vehicle demo hadn't exercised. All
three are fixed in the current code; documented here because they're good
"how did you validate this" material for the viva.

**(a) Discretized SOC transitions can have a self-loop that erases slow
charging entirely.** `nearest_soc_bucket_index` originally rounded a
computed `soc_after` to a single bucket. With `SOC_STEP = 5`, a 5 kW
charger on a large battery can gain less than 2.5 percentage points per
15-minute slot — under half a bucket width — so the transition rounded
right back to the *same* bucket every single slot, forever. Backward
induction correctly concluded "this action never changes anything," and a
slow-charging vehicle in the fleet simulation received **zero** charge for
its entire session despite having an hour of idle charger time available.
Fixed with `soc_transition_distribution` (`optimization/mdp.py`): linear
interpolation between the two bracketing buckets, weighted so the
*expected* next bucket matches the true continuous outcome. Small gains
now correctly accumulate probability mass toward the next bucket over
successive slots instead of being discarded outright.

**(b) A tie-break attempt introduced a real indexing bug.** While chasing
(a) — before finding the actual cause — actions were reordered to iterate
largest-power-first, hoping ties would resolve toward "charge" over "don't
charge." That reordering exposed a latent bug: the code initializing
`best_action_idx` on the first action processed hardcoded `np.zeros(...)`
regardless of which action index was actually being processed. This had
been silently correct only because, in the original ascending order, the
first action processed always happened to be index 0 (0 kW) — reordering
broke that coincidence and made the bug visible: the *value* (`V`) was
computed correctly, but the *policy* array recorded "0 kW" even when a
much larger action was actually optimal. Fixed by initializing
`best_action_idx` to the current action's real index, and (once (a) made
the reordering unnecessary) reverted to natural ascending order — ties now
correctly default to 0 kW, which is the sensible interpretation of "no
action strictly helps."

**(c) Cost terms normalized against a vehicle's own max rate made weak
chargers look artificially expensive.** `electricity_cost`, `grid_penalty`,
and `renewable_reward` were originally normalized by dividing by *that
vehicle's own* `max_charge_rate_kw`. This means drawing 5 kW registered as
"71% of capacity, quite expensive" for a car on a 7 kW charger, but only
"10% of capacity, cheap" for a car on a 50 kW charger — even though 5 kW is
the same, genuinely small, real-world grid draw either way. The practical
effect: a vehicle stuck with a slow charger and a tight deadline was
recommended 0 kW for its *entire* session, even though charging had no
downside and it desperately needed the energy. Fixed by normalizing those
three terms against `GLOBAL_REFERENCE_MAX_KW` (the largest configured
action, 50 kW) instead — a fixed, vehicle-independent reference — while
deliberately leaving battery degradation's charging-rate term
vehicle-relative, since stressing a car's *own* limit is what actually
matters for wear (`optimization/reward_model.py`).

All three were only visible once the SDP was tested inside a *fleet*
simulation with heterogeneous vehicles (different battery sizes, charge
rates, and deadlines) — a single "one nice EV, one plausible scenario" demo
had accidentally avoided every one of these edge cases. This is itself a
methodological point worth making in the viva: single-scenario demos are
weak validation for a discretized stochastic optimizer; a fleet of diverse,
randomly generated vehicles is what actually exercises the state space.
