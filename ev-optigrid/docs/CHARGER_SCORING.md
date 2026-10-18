# Charging Opportunity Score (COS)

The project's original station-ranking metric (spec §4). Every candidate
station in a search result gets a 0–100 score; higher is better under the
active profile.

## Formula

```
COS = 100 * ( w_cost*cost_score + w_time*time_score + w_queue*queue_score
            + w_distance*distance_score + w_battery*battery_score
            + w_grid*grid_score + w_renewable*renewable_score
            + w_availability*availability_score ) / total_weight
```

`optimization/station_optimizer.py::compute_cos_scores`.

## Normalization: relative to the current candidate set

Each raw attribute (₹, km, minutes, %) is min-max normalized **across the
stations currently being compared** — not against a fixed global scale.
"distance_score" answers "how good is this station's distance relative to
the other candidates in this result", which is the right question for a
ranking metric: its job is to order *this* list. It sidesteps having to
invent defensible absolute bounds for every unit, and means a search in a
dense city center and one in a sparse rural area both produce a sensible
0–100 spread instead of everything clustering near one end of an
arbitrary global scale.

Cost-like attributes (cost, time, queue wait, distance, battery impact,
grid load) are inverted so **lower is better → higher score**. Benefit-like
attributes (renewable availability, connector availability) are kept
direct. When every candidate ties on an attribute, that attribute
contributes full marks to everyone rather than dividing by zero
(`_minmax_goodness`).

## Weights depend on user preference (verified, not assumed)

The same six profiles as the SDP (save_money / fastest / battery_health /
green / balanced / custom) each carry their own `COSWeights`. Verified in
`tests/optimization/test_station_optimizer.py::test_profile_switch_changes_winner`:
given two stations — one cheap-but-slow, one pricey-but-fast — `save_money`
picks the cheap one and `fastest` picks the pricey one, from the exact same
candidate data. Switching profile is capable of changing which station is
#1, not just re-shuffling the charging *rate* decision.

## Inputs, and where they come from

| COS component | Source (Phase 12 wiring) |
|---|---|
| charging_cost | `real_electricity_cost()` at the station's connector price × predicted session duration |
| travel_time + charging_duration | `services/providers/base.py::RouteResult` + session length estimate |
| predicted_wait | `ml/queue_predictor.py` |
| distance | haversine from the user's location |
| battery_impact | `optimization/battery_model.py::compute_degradation_cost` |
| grid_load | live/predicted grid load at charging time |
| renewable_availability | live/predicted solar fraction |
| connector_availability | live connector status count from the station provider |

## Why this is a genuine metric, not a cosmetic score

Every input is either a real provider response (tagged `source`) or the
output of an already-tested module (COS never invents its own numbers) —
consistent with spec §42 ("do not create a fake UI around fake
calculations"). Re-running `rank_stations` on a changed candidate set (a
station drops offline, a queue prediction updates) recomputes every score
from scratch; nothing is cached or memoized at this layer, since it's cheap
enough (pure arithmetic over a handful of candidates) that recomputing is
simpler and safer than invalidation logic.
