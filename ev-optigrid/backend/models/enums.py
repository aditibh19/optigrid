"""
Shared enums.

`DataSource` is used on every table that can hold either live, simulated, or
model-predicted data. This is a hard project rule (see spec §29/§42): the UI
must never present simulated/demo data as if it were live real-world data,
so the label travels with the row from the database outward.
"""
import enum


class DataSource(str, enum.Enum):
    REAL = "real"
    SIMULATED = "simulated"
    PREDICTED = "predicted"
    DEMO = "demo"


class OptimizationProfile(str, enum.Enum):
    SAVE_MONEY = "save_money"
    FASTEST = "fastest"
    BATTERY_HEALTH = "battery_health"
    GREEN = "green"
    BALANCED = "balanced"
    CUSTOM = "custom"


class ConnectorType(str, enum.Enum):
    AC_TYPE2 = "ac_type2"
    DC_CCS = "dc_ccs"
    DC_CHADEMO = "dc_chademo"
    DC_FAST = "dc_fast"


class ChargerStatus(str, enum.Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    OUT_OF_SERVICE = "out_of_service"
    UNKNOWN = "unknown"


class SessionType(str, enum.Enum):
    REAL = "real"
    SIMULATED = "simulated"


class JourneyStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PredictionType(str, enum.Enum):
    PRICE = "price"
    GRID = "grid"
    SOLAR = "solar"
    QUEUE = "queue"
    DEMAND = "demand"


class RecommendedAction(str, enum.Enum):
    CHARGE_NOW = "charge_now"
    WAIT = "wait"
    CHARGE_PARTIAL = "charge_partial"
    CHARGE_FULL = "charge_full"
    CHANGE_STATION = "change_station"
    USE_FAST_CHARGER = "use_fast_charger"
    USE_SLOW_CHARGER = "use_slow_charger"


class FleetVehicleStatus(str, enum.Enum):
    WAITING = "waiting"
    CHARGING = "charging"
    COMPLETED = "completed"
