Viva Guide

What problem is being solved?
Deciding when, where, and how much to charge an EV depends on the journey ahead, battery state, nearby charger availability/queues, electricity price and grid load (now and predicted), renewables, battery health trade-offs, and user priorities -- all changing over time and uncertain in advance. EV-OptiGrid treats this as one sequential decision problem under uncertainty rather than a static "cheapest charger near me" lookup.

Why EV charging optimization specifically?
A bounded, high-stakes sequential decision problem: a known/estimable deadline, a clear multi-part objective, real uncertainty (price, grid, queues), and measurable payoff (money saved, battery life preserved) -- good ground for demonstrating stochastic optimization with consequences anyone can understand.

Why stochastic dynamic programming, not something simpler?
Greedy ("charge now at max") ignores that conditions change before the deadline. Fixed-threshold ignores the deadline and can miss the target. SDP optimizes expected cost over the distribution of plausible futures the Markov model assigns, subject to the deadline. All three simpler methods are implemented as baselines (simulation/baseline_policies.py) specifically so this claim is measured, not asserted (see docs/ALGORITHM.md's "measured result" line: SDP beats greedy ~28% on cost, ~2.5x on renewable utilization, in exchange for somewhat more deadline violations under heavy contention).

What is the state?
(soc_bucket, price_bucket, grid_load_bucket, solar_bucket) -- 21 x 3 x 3 x 3 = 567 discrete states per time slot. Time-to-deadline is NOT a state dimension -- it is the backward-induction index itself. Full rationale in docs/MDP.md.

What is the action?
Charging power from a configurable discrete set (0,5,10,...,50 kW by default), capped per-session at min(vehicle max, charger max).

What is the reward/cost?
Per-slot: normalized electricity cost + battery degradation + grid-peak penalty - renewable reward. Terminal (at deadline): penalty for missing target SOC, more severe penalty for falling below minimum safe SOC. Full formula in docs/MDP.md.

What is value iteration, here specifically?
Finite-horizon backward induction, not the textbook infinite-horizon discounted form: solve the terminal cost at the deadline slot, then work backward one slot at a time, at each state picking the action minimizing immediate cost plus discounted expected future value under the Markov transition model. Solved exactly since the discretized space is small.

Why use ML if the SDP already handles uncertainty?
The SDP needs a transition model and current-state estimate -- that's what the five ML forecasters (price/grid/solar/queue/trip-demand) supply. ML estimates the world; SDP optimizes against it. They are complementary, not competing. Metrics in docs/ML.md.

Why is the system personalized?
"Optimal" depends on what the user cares about -- cost, speed, battery life, emissions trade off differently for different users. One cost function, six swappable weight profiles, verified to change behavior at two layers: the SDP's charging-rate decision and the station-ranking COS (different profiles pick different #1 stations from the identical candidate list).

How are chargers selected?
Charging Opportunity Score (docs/CHARGER_SCORING.md): every candidate scored 0-100 from real inputs (cost, travel+charge time, predicted queue, distance, battery impact, grid load, renewable availability, connector availability), min-max normalized across the current candidate set, weighted by the active profile.

How is uncertainty handled?
Two layers: ML point predictions, and SDP Markov transition matrices capturing a distribution over how price/grid/solar evolve, with the Bellman recursion optimizing expected cost over that distribution rather than one forecasted path.

How does re-optimization work?
A detected change (price update, station unavailable, queue increase, deadline change, grid spike) triggers a NEW optimization run, never an edit of the old one. The old result is marked stale with a pointer to what superseded it, so "why did the plan change" has a concrete, auditable answer.

What happens when the target is infeasible?
The system reports the truth instead of pretending: it solves for the maximum achievable SOC at max power over the remaining horizon and says e.g. "90% is infeasible before departure; maximum achievable SOC is 68%." Verified end-to-end in tests/backend/test_optimization_service.py.

What are the system's limitations? (state proactively)
- Discretization is coarse by design (3 price/grid/solar levels, 5% SOC steps) to stay exactly solvable in well under a second.
- Price/grid/solar modeled as independent Markov chains, though correlated in reality -- documented simplification.
- Battery degradation model is illustrative, not validated against real aging data.
- All ML datasets are synthetic until real historical data accumulates -- metrics validate the pipeline, not real-world accuracy.
- The multi-EV allocator is a greedy heuristic, not a provably optimal assignment solve, chosen for speed and constraint-safety by construction.
- The AI Copilot's extraction is rule-based (regex/keyword) in this build, not a real LLM -- the architecture supports swapping one in for extraction only, never for the decision itself.

"How did you validate this actually works?"
Three real bugs were found specifically by testing the SDP inside a fleet simulation with heterogeneous vehicles rather than one hand-picked demo: a discretization self-loop that erased slow charging entirely, an action-indexing bug found while chasing that, and a cost-normalization issue that made weak chargers look artificially expensive. All three are written up with the debugging process in docs/MDP.md. 289 backend tests, 23 frontend tests and a 36-check live end-to-end run currently pass. Beyond the SDP bugs, testing the backend and frontend for real found a further set (nine in the backend and simulator, ten more in security and packaging: no endpoint checked a token, model files written non-atomically, an XGBoost fallback that didn't catch a macOS load failure, a PostgreSQL default that broke first run on a laptop) — all listed in docs/TESTING.md, each with a regression test.


## Where to find things during the viva

- "Show me the Bellman equation working": the **Bellman equation** page. It recomputes one state action by action and shows a
  green check that it matches the solver's own value function and policy.
- "Is it actually better than charging immediately?": the **Monte Carlo** page (paired scenarios, 95% confidence interval) and the
  **Digital twin**. Be ready to state the trade-off it shows: under the balanced profile it saves money by accepting a lower final charge.
- "Why not just round the battery level to the nearest bucket?": the **State space** page, "How the battery level moves".
- "What did you leave out?": `docs/SYNOPSIS_TRACEABILITY.md` (Tailwind not used, no Redis, traffic not modelled, MQTT not wired,
  synthetic data) and the "What is still NOT verified" list in `docs/TESTING.md`.
- "How do you know the optimiser is right?": value function checked against an independent recomputation (Bellman page);
  monotonicity tests (dearer power or a stressed grid never increases charging); three real bugs found and fixed (`docs/MDP.md`).
