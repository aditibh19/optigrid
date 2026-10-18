# Battery Health / Degradation Model

**Scope disclaimer (repeat this in the viva if asked):** this is a
simplified, illustrative model used to give the optimizer *some* signal to
trade off "charge fast now" against "charge gently later". It is **not** a
validated electrochemical aging model and does not predict real battery
lifespan. Real degradation depends on cell chemistry, manufacturing
tolerances, and usage history that this project has no access to.

## Model (`optimization/battery_model.py`)

```
degradation_cost = k_dod   * depth_of_discharge_term(soc_before, soc_after)
                  + k_soc  * high_soc_exposure_term(soc_after)
                  + k_rate * high_charging_power_term(charge_kw, max_kw)
                  + k_temp * temperature_term(ambient_c)   # optional, 0 if absent
```

Each term is normalized to roughly `[0, 1]` before weighting, so
`degradation_cost` stays on the same scale as the other terms in the
multi-objective cost function (`docs/MDP.md` §8 covers why this matters —
we hit a real bug from *not* normalizing electricity cost the same way).

| Term | Rationale | Shape |
|---|---|---|
| Depth of discharge | Large SOC swings stress the cell more than shallow ones | `(Δsoc/100)^1.2` — mildly convex |
| High-SOC exposure | Sitting above ~80% SOC accelerates degradation in most Li-ion chemistries | 0 below threshold, linear ramp to 1 at 100% |
| Charging rate | Charging near max rate stresses the cell more than trickle charging | `(power/max_power)^1.5` |
| Temperature (optional) | Extreme heat/cold increases stress | U-shaped around ~20°C, 0 if no data |

## From per-event cost to a displayed health indicator

`battery_health_indicator(cumulative_cost, scale)` maps the running sum of
`degradation_cost` over the vehicle's simulated lifetime to a 0–100 display
number:

```
health = 100 * max(0, 1 - cumulative_cost / scale)
```

`scale` is tuned so a few years of realistic synthetic usage lands in a
plausible 70–100% band — again, tuned for a believable *demo*, not
calibrated against real degradation data.

## Where this feeds into the system

- Per-slot inside the SDP's cost function (`w_battery` weight, highest for
  the `battery_health` profile).
- Displayed on the **Battery Health** page as the 0–100 indicator plus a
  breakdown of which term (DoD / high-SOC / fast-charging) is contributing
  most, computed from actual logged `charging_sessions`, not invented.
