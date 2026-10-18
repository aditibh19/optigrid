"""
Journey energy model (Phase 11, spec §5).

Answers: "given this route and this vehicle, how much energy does the trip
need, and can the vehicle make it without charging?" This is the
physics-based baseline; `ml/demand_predictor.py` (Phase 8) offers a
learned refinement once real trip data exists, but this model is always
available (no training data needed) and is what the ML model's predictions
get sanity-checked against.

Deliberately DB- and FastAPI-independent (only needs the provider
interfaces' plain dataclasses), so it's directly testable without any
optional dependency installed.
"""
from dataclasses import dataclass

from services.providers.base import RouteResult


@dataclass
class VehicleEnergyProfile:
    battery_capacity_kwh: float
    efficiency_kwh_per_km: float
    current_soc_pct: float


@dataclass
class JourneyEnergyResult:
    energy_required_kwh: float
    expected_arrival_soc_pct: float
    minimum_safe_soc_pct: float
    is_feasible_without_charging: bool
    soc_shortfall_pct: float   # 0 if feasible; how far below minimum_safe it would land otherwise


# Safety margin kept in reserve beyond the bare energy requirement, so the
# vehicle doesn't arrive at exactly 0% (no buffer for detours, AC/heating
# draw, or route estimate error). Expressed as a percentage of the trip's
# own energy requirement, not a flat SOC number, so it scales sensibly for
# both short hops and long trips.
SAFETY_MARGIN_FRACTION = 0.15


def estimate_journey_energy(
    route: RouteResult,
    vehicle: VehicleEnergyProfile,
    traffic_multiplier: float = 1.0,
    elevation_gain_m: float = 0.0,
    elevation_cost_kwh_per_m: float = 0.00025,
) -> JourneyEnergyResult:
    """
    Physics-based estimate, mirroring the terms `ml/demand_predictor.py`
    was trained to recover: distance x efficiency x traffic, plus a small
    elevation-gain term. Elevation is optional (spec §5: "Optional
    elevation") — defaults to 0 when unavailable.
    """
    base_energy_kwh = route.distance_km * vehicle.efficiency_kwh_per_km * traffic_multiplier
    elevation_energy_kwh = elevation_gain_m * elevation_cost_kwh_per_m
    energy_required_kwh = base_energy_kwh + elevation_energy_kwh

    soc_consumed_pct = (energy_required_kwh / vehicle.battery_capacity_kwh) * 100.0
    expected_arrival_soc_pct = vehicle.current_soc_pct - soc_consumed_pct

    minimum_safe_soc_pct = max(0.0, (SAFETY_MARGIN_FRACTION * energy_required_kwh
                                      / vehicle.battery_capacity_kwh) * 100.0)

    is_feasible = expected_arrival_soc_pct >= minimum_safe_soc_pct
    shortfall = max(0.0, minimum_safe_soc_pct - expected_arrival_soc_pct)

    return JourneyEnergyResult(
        energy_required_kwh=round(energy_required_kwh, 2),
        expected_arrival_soc_pct=round(expected_arrival_soc_pct, 1),
        minimum_safe_soc_pct=round(minimum_safe_soc_pct, 1),
        is_feasible_without_charging=is_feasible,
        soc_shortfall_pct=round(shortfall, 1),
    )


def required_charge_before_departure(
    journey: JourneyEnergyResult,
    vehicle: VehicleEnergyProfile,
    target_arrival_buffer_pct: float = 20.0,
) -> float:
    """
    If the journey isn't feasible as-is, how much SOC (percentage points)
    would the vehicle need to gain BEFORE departure to arrive with at least
    `target_arrival_buffer_pct` remaining? Returns 0 if already feasible
    with that buffer.
    """
    consumption_pct = (journey.energy_required_kwh / vehicle.battery_capacity_kwh) * 100.0
    needed_departure_soc = consumption_pct + target_arrival_buffer_pct
    gap = needed_departure_soc - vehicle.current_soc_pct
    return round(max(0.0, gap), 1)
