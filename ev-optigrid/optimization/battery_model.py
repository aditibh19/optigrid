"""
Simplified EV battery degradation model.

ACADEMIC SCOPE NOTE (repeated in docs/BATTERY_MODEL.md and shown in the UI):
this is a simplified, illustrative degradation model for optimization
purposes. It is NOT a validated electrochemical aging model and must not be
presented as predicting real battery lifespan. It exists so the optimizer
has *some* signal to trade off "charge fast now" against "charge gently
later", which is the academically relevant part.

Model (a common simplified linear/quadratic-penalty style used in EV
smart-charging literature):

  degradation_cost = k_dod   * depth_of_discharge_term
                    + k_soc  * high_soc_exposure_term
                    + k_rate * high_charging_power_term
                    + k_temp * temperature_term   (optional, defaults to 0)

Each term is normalized to [0, 1] before weighting so the resulting
`degradation_cost` is comparable in scale to the other cost terms in the
multi-objective function (reward_model.py).
"""
from dataclasses import dataclass


@dataclass
class BatteryDegradationWeights:
    k_dod: float = 0.30
    k_high_soc: float = 0.25
    k_charge_rate: float = 0.35
    k_temperature: float = 0.10


def depth_of_discharge_term(soc_before: float, soc_after: float) -> float:
    """Larger full-range swings are penalized more than shallow ones."""
    dod = abs(soc_after - soc_before) / 100.0
    return dod ** 1.2  # mildly convex: big swings cost disproportionately more


def high_soc_exposure_term(soc_after: float, threshold: float = 80.0) -> float:
    """
    Time spent above `threshold`% SOC accelerates degradation in most
    lithium-ion chemistries. Returns 0 below the threshold, ramping to 1 at
    100%.
    """
    if soc_after <= threshold:
        return 0.0
    return (soc_after - threshold) / (100.0 - threshold)


def high_charging_power_term(charge_power_kw: float, max_charge_rate_kw: float) -> float:
    """Charging near the vehicle's max rate stresses the battery more than trickle charging."""
    if max_charge_rate_kw <= 0:
        return 0.0
    return min(1.0, charge_power_kw / max_charge_rate_kw) ** 1.5


def temperature_term(ambient_temp_c: float | None) -> float:
    """
    Optional. Very high or very low ambient temperature increases stress.
    Returns 0 if temperature data isn't available (feature is optional per
    spec §9), otherwise a U-shaped penalty centered on ~20°C.
    """
    if ambient_temp_c is None:
        return 0.0
    ideal = 20.0
    spread = 25.0
    return min(1.0, ((ambient_temp_c - ideal) / spread) ** 2)


def compute_degradation_cost(
    soc_before: float,
    soc_after: float,
    charge_power_kw: float,
    max_charge_rate_kw: float,
    ambient_temp_c: float | None = None,
    weights: BatteryDegradationWeights = BatteryDegradationWeights(),
) -> float:
    """Returns a normalized degradation cost in roughly [0, 1]."""
    dod = depth_of_discharge_term(soc_before, soc_after)
    high_soc = high_soc_exposure_term(soc_after)
    rate = high_charging_power_term(charge_power_kw, max_charge_rate_kw)
    temp = temperature_term(ambient_temp_c)

    return (
        weights.k_dod * dod
        + weights.k_high_soc * high_soc
        + weights.k_charge_rate * rate
        + weights.k_temperature * temp
    )


def battery_health_indicator(cumulative_degradation_cost: float, scale: float = 500.0) -> float:
    """
    Maps accumulated (unitless) degradation cost over the vehicle's lifetime
    to a 0-100 "health" indicator for display purposes. `scale` controls how
    much cumulative cost corresponds to a fully degraded (0%) indicator —
    tuned so realistic multi-year synthetic usage lands in a plausible
    70-100% band; NOT calibrated against real degradation data.
    """
    health = 100.0 * max(0.0, 1.0 - cumulative_degradation_cost / scale)
    return round(health, 2)
