"""
EV / battery simulator (Phase 3).

Pure, dependency-light physics used by BOTH:
  - the MDP transition model (deterministic part of the state transition), and
  - the What-If Simulator (simulation/ev_simulator.py's higher-level fleet loop
    calls into this for each individual vehicle's SOC update).

Everything here is a simplified, clearly-labeled *model* — not a claim about
real battery chemistry (see docs/BATTERY_MODEL.md).
"""
from dataclasses import dataclass


@dataclass
class VehicleSpec:
    battery_capacity_kwh: float
    efficiency_kwh_per_km: float          # energy consumption while driving
    max_charge_rate_kw: float
    charging_efficiency: float = 0.90     # AC/DC conversion + battery charge losses


@dataclass
class EVState:
    soc_pct: float                        # 0-100
    battery_health_pct: float = 100.0     # simulated degradation indicator (see battery_model.py)


def clamp_soc(soc_pct: float) -> float:
    return max(0.0, min(100.0, soc_pct))


def soc_gain_from_charging(
    vehicle: VehicleSpec,
    charge_power_kw: float,
    duration_hours: float,
) -> float:
    """
    Percentage-point SOC gained from charging at `charge_power_kw` for
    `duration_hours`, accounting for charging losses. Charge power is
    capped at the vehicle's and (implicitly, by the caller) the charger's
    max rate.
    """
    power = min(charge_power_kw, vehicle.max_charge_rate_kw)
    energy_delivered_kwh = power * duration_hours * vehicle.charging_efficiency
    return (energy_delivered_kwh / vehicle.battery_capacity_kwh) * 100.0


def soc_loss_from_driving(
    vehicle: VehicleSpec,
    distance_km: float,
    traffic_multiplier: float = 1.0,
) -> float:
    """
    Percentage-point SOC consumed driving `distance_km`. `traffic_multiplier`
    (>=1.0) inflates consumption for congestion/stop-start driving.
    """
    energy_used_kwh = vehicle.efficiency_kwh_per_km * distance_km * traffic_multiplier
    return (energy_used_kwh / vehicle.battery_capacity_kwh) * 100.0


def apply_charging_step(
    vehicle: VehicleSpec,
    state: EVState,
    charge_power_kw: float,
    duration_hours: float,
) -> EVState:
    gain = soc_gain_from_charging(vehicle, charge_power_kw, duration_hours)
    return EVState(
        soc_pct=clamp_soc(state.soc_pct + gain),
        battery_health_pct=state.battery_health_pct,  # degradation applied separately (battery_model.py)
    )


def apply_driving_step(
    vehicle: VehicleSpec,
    state: EVState,
    distance_km: float,
    traffic_multiplier: float = 1.0,
) -> EVState:
    loss = soc_loss_from_driving(vehicle, distance_km, traffic_multiplier)
    return EVState(
        soc_pct=clamp_soc(state.soc_pct - loss),
        battery_health_pct=state.battery_health_pct,
    )
