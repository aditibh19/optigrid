"""
Demo providers (Phase 10, spec §2/§30) — used whenever no real API key is
configured (`database/config.py::Settings.is_demo_mode`), so the whole
platform is runnable and demonstrable with zero external accounts.

Every object returned here is tagged `source="demo"` and is deterministic
given the same inputs (seeded), so demos and tests are reproducible — never
presented to the user as live real-world data (spec §29: "Never fabricate
real-world station availability").
"""
import hashlib
import math

from services.providers.base import (
    LocationProvider, RoutingProvider, ChargingStationProvider, WeatherProvider, LLMProvider,
    Coordinates, RouteResult, StationInfo, WeatherInfo,
)


def _seed_from_string(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


def _haversine_km(a: Coordinates, b: Coordinates) -> float:
    R = 6371.0
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = math.radians(b.lat - a.lat)
    dlng = math.radians(b.lng - a.lng)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(h))


class DemoLocationProvider(LocationProvider):
    """
    Resolves a place name to coordinates by deterministically hashing the
    query into a small offset from a configurable reference point — good
    enough to demo "search for a location" without a real geocoding API.
    """
    def __init__(self, reference: Coordinates = Coordinates(lat=28.6139, lng=77.2090)):  # New Delhi
        self.reference = reference

    def geocode(self, query: str) -> Coordinates:
        seed = _seed_from_string(query.strip().lower())
        offset_lat = ((seed % 1000) / 1000.0 - 0.5) * 0.3   # +/- ~0.15 degrees (~15km)
        offset_lng = (((seed // 1000) % 1000) / 1000.0 - 0.5) * 0.3
        return Coordinates(lat=self.reference.lat + offset_lat, lng=self.reference.lng + offset_lng)


class DemoRoutingProvider(RoutingProvider):
    """
    Straight-line-distance-based route estimate, inflated by a fixed
    road-network factor (real roads are never perfectly straight) — no
    external routing API involved. `source="demo"`.
    """
    ROAD_NETWORK_FACTOR = 1.35   # real road distance is typically 1.2-1.5x straight-line
    ASSUMED_AVG_SPEED_KMH = 40.0

    def get_route(self, origin: Coordinates, destination: Coordinates) -> RouteResult:
        straight_km = _haversine_km(origin, destination)
        distance_km = straight_km * self.ROAD_NETWORK_FACTOR
        duration_min = (distance_km / self.ASSUMED_AVG_SPEED_KMH) * 60.0
        return RouteResult(distance_km=round(distance_km, 2), duration_min=round(duration_min, 1),
                            polyline=None, origin=origin, destination=destination, source="demo")


class DemoChargingStationProvider(ChargingStationProvider):
    """
    Deterministically generates a handful of plausible stations around a
    location (or along a route), seeded by the location itself so repeated
    calls for the same area return the same stations — `source="demo"`.
    Never claims real-world availability (spec §29).
    """
    CONNECTOR_TEMPLATES = [
        {"connector_type": "dc_fast", "power_kw": 120.0, "price_per_kwh": 8.2},
        {"connector_type": "dc_ccs", "power_kw": 50.0, "price_per_kwh": 7.5},
        {"connector_type": "ac_type2", "power_kw": 7.4, "price_per_kwh": 5.0},
    ]
    STATUSES = ["available", "available", "available", "occupied", "out_of_service"]

    def _generate_station(self, index: int, center: Coordinates, max_offset_km: float) -> StationInfo:
        seed = _seed_from_string(f"{center.lat:.4f}:{center.lng:.4f}:{index}")
        deg_offset = (max_offset_km / 111.0)  # ~111km per degree latitude
        offset_lat = (((seed % 1000) / 1000.0) - 0.5) * 2 * deg_offset
        offset_lng = ((((seed // 1000) % 1000) / 1000.0) - 0.5) * 2 * deg_offset

        n_connectors = 1 + (seed % 3)
        connectors = []
        for c in range(n_connectors):
            template = self.CONNECTOR_TEMPLATES[(seed + c) % len(self.CONNECTOR_TEMPLATES)]
            status = self.STATUSES[(seed + c * 7) % len(self.STATUSES)]
            connectors.append({**template, "status": status})

        return StationInfo(
            station_id=f"demo-station-{seed}",
            name=f"Demo Charging Point {index + 1}",
            lat=center.lat + offset_lat, lng=center.lng + offset_lng,
            address=None, connectors=connectors, source="demo",
        )

    def find_nearby(self, location: Coordinates, radius_km: float, limit: int = 10) -> list[StationInfo]:
        n = min(limit, 6)
        return [self._generate_station(i, location, radius_km) for i in range(n)]

    def find_along_route(self, route: RouteResult, corridor_km: float = 2.0, limit: int = 10) -> list[StationInfo]:
        # Demo simplification: without real polyline geometry, scatter
        # stations around the route's straight-line midpoint as a stand-in
        # for "along the route". A real routing provider's polyline would
        # let us sample actual points along the path instead.
        midpoint = Coordinates(
            lat=(route.origin.lat + route.destination.lat) / 2,
            lng=(route.origin.lng + route.destination.lng) / 2,
        )
        n = min(limit, 4)
        return [self._generate_station(100 + i, midpoint, corridor_km) for i in range(n)]


class DemoWeatherProvider(WeatherProvider):
    def get_current(self, location: Coordinates) -> WeatherInfo:
        seed = _seed_from_string(f"{location.lat:.2f}:{location.lng:.2f}")
        temp = 18.0 + (seed % 20)  # 18-38°C, deterministic
        conditions = ["clear", "partly cloudy", "cloudy", "light rain"]
        return WeatherInfo(temperature_c=float(temp), condition=conditions[seed % len(conditions)], source="demo")


class DemoLLMProvider(LLMProvider):
    """
    Not a real language model — a fixed acknowledgement string. Used only
    so the AI Copilot's plumbing (extraction -> validation -> optimizer ->
    explanation) is exercisable end-to-end without an API key. The
    parameter EXTRACTION step in `backend/services/copilot_service.py` uses
    its own rule-based parser rather than this provider, precisely so the
    copilot demo doesn't silently depend on a real LLM being configured.
    """
    def complete(self, system_prompt: str, user_message: str) -> str:
        return f"[demo LLM — no real model configured] Acknowledged: {user_message[:80]}"
