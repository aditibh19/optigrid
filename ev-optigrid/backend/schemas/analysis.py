"""Request schemas for the analysis, digital-twin, fleet and battery endpoints."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ProfileName = Literal["balanced", "save_money", "fastest", "battery_health", "green"]


class PolicyParams(BaseModel):
    """Everything that defines one solved MDP (same knobs as /api/charging/optimize)."""
    battery_capacity_kwh: float = Field(60.0, gt=0, le=500)
    max_charge_rate_kw: float = Field(50.0, gt=0, le=350)
    target_soc_pct: float = Field(90.0, ge=0, le=100)
    minimum_safe_soc_pct: float = Field(70.0, ge=0, le=100)
    horizon_slots: int = Field(24, ge=2, le=96)
    slot_minutes: int = Field(15, ge=1, le=120)
    profile: ProfileName = "balanced"

    @model_validator(mode="after")
    def _safe_not_above_target(self):
        if self.minimum_safe_soc_pct > self.target_soc_pct:
            raise ValueError("minimum_safe_soc_pct cannot be above target_soc_pct")
        return self


class Conditions(BaseModel):
    """Where the world is right now; bucketed into the MDP's low/medium/high levels."""
    current_soc_pct: float = Field(32.0, ge=0, le=100)
    current_price_per_kwh: float = Field(8.0, ge=0, le=1000)
    current_grid_load_pct: float = Field(60.0, ge=0, le=100)
    current_solar_availability_frac: float = Field(0.2, ge=0, le=1)


Level = Field(1, ge=0, le=2)


class HeatmapRequest(PolicyParams):
    mode: Literal["soc_by_time", "soc_by_level"] = "soc_by_time"
    vary: Literal["price", "grid", "solar"] = "price"     # used when mode == soc_by_level
    t: int = Field(0, ge=0)                                # used when mode == soc_by_level
    price_level: int = Level
    grid_level: int = Level
    solar_level: int = Level


class BellmanRequest(PolicyParams):
    t: int = Field(0, ge=0)
    soc_pct: float = Field(30.0, ge=0, le=100)
    price_level: int = Level
    grid_level: int = Level
    solar_level: int = Level


class MonteCarloRequest(PolicyParams, Conditions):
    n_runs: int = Field(500, ge=10, le=2000)
    seed: int = 42


class SensitivityRequest(PolicyParams, Conditions):
    sweep: Literal["soc", "price", "grid", "solar", "profile", "cost_weight"] = "soc"


class TwinRequest(PolicyParams, Conditions):
    seed: int = 7


class FleetVehicle(BaseModel):
    vehicle_id: int = Field(..., ge=0)
    name: str = Field(..., min_length=1, max_length=60)
    current_soc_pct: float = Field(..., ge=0, le=100)
    target_soc_pct: float = Field(80.0, ge=0, le=100)
    battery_capacity_kwh: float = Field(60.0, gt=0, le=500)
    max_charge_rate_kw: float = Field(50.0, gt=0, le=350)
    urgency: int = Field(3, ge=1, le=5)                    # 5 = must be ready first
    deadline_hours: float = Field(2.0, gt=0, le=48)


class FleetCharger(BaseModel):
    charger_id: int = Field(..., ge=0)
    power_kw: float = Field(..., gt=0, le=1000)


class FleetRequest(BaseModel):
    vehicles: list[FleetVehicle] = Field(..., min_length=1, max_length=60)
    chargers: list[FleetCharger] = Field(..., min_length=1, max_length=30)
    grid_capacity_kw: float = Field(..., gt=0, le=100000)
    charging_efficiency: float = Field(0.90, gt=0, le=1)

    @model_validator(mode="after")
    def _unique_ids(self):
        if len({v.vehicle_id for v in self.vehicles}) != len(self.vehicles):
            raise ValueError("vehicle_id values must be unique")
        if len({c.charger_id for c in self.chargers}) != len(self.chargers):
            raise ValueError("charger_id values must be unique")
        return self
