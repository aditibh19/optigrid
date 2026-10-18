"""
Provider interfaces (Phase 10, spec §2/§39).

Every external integration (maps/routing, charging-station discovery,
weather, LLM) is accessed only through one of these interfaces. Business
logic (services/, optimization/) depends on the interface type, never on a
concrete provider class — so swapping `DemoRoutingProvider` for
`MapboxRoutingProvider` later touches one place (the factory in
`provider_factory.py`) and nothing else. This is what makes DEMO MODE
possible with zero API keys (spec §29/§30) and what keeps provider-specific
logic from leaking throughout the application (spec §39).

Every data object returned by a provider carries a `source` field
(`models.enums.DataSource` in the backend) so the UI can label it
correctly — this module doesn't import that enum directly (to stay
DB-independent and unit-testable without SQLAlchemy installed), but every
concrete provider's docstring states which source label its output should
carry.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Coordinates:
    lat: float
    lng: float


@dataclass
class RouteResult:
    distance_km: float
    duration_min: float
    polyline: str | None
    origin: Coordinates
    destination: Coordinates
    source: str   # "real" | "demo"


@dataclass
class StationInfo:
    station_id: str
    name: str
    lat: float
    lng: float
    address: str | None
    connectors: list[dict]   # [{"connector_type": str, "power_kw": float, "price_per_kwh": float, "status": str}, ...]
    source: str   # "real" | "demo"


@dataclass
class WeatherInfo:
    temperature_c: float
    condition: str
    source: str   # "real" | "demo"


class LocationProvider(ABC):
    """Resolves a human-entered place into coordinates (manual entry fallback path, spec §2)."""

    @abstractmethod
    def geocode(self, query: str) -> Coordinates:
        ...


class RoutingProvider(ABC):
    @abstractmethod
    def get_route(self, origin: Coordinates, destination: Coordinates) -> RouteResult:
        ...


class ChargingStationProvider(ABC):
    @abstractmethod
    def find_nearby(self, location: Coordinates, radius_km: float, limit: int = 10) -> list[StationInfo]:
        ...

    @abstractmethod
    def find_along_route(self, route: RouteResult, corridor_km: float = 2.0, limit: int = 10) -> list[StationInfo]:
        ...


class WeatherProvider(ABC):
    @abstractmethod
    def get_current(self, location: Coordinates) -> WeatherInfo:
        ...


class LLMProvider(ABC):
    """Used only for the AI Copilot's parameter extraction / explanation phrasing (spec §14) —
    never for making the charging decision itself."""

    @abstractmethod
    def complete(self, system_prompt: str, user_message: str) -> str:
        ...
