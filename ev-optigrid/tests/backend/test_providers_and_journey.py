import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import pytest

from services.providers.base import Coordinates
from services.providers.demo_providers import (
    DemoLocationProvider, DemoRoutingProvider, DemoChargingStationProvider, DemoWeatherProvider,
)
from services.journey_service import VehicleEnergyProfile, estimate_journey_energy, required_charge_before_departure


# ── Demo providers ──────────────────────────────────────────────────────

def test_geocode_deterministic():
    loc = DemoLocationProvider()
    c1 = loc.geocode("Connaught Place")
    c2 = loc.geocode("Connaught Place")
    assert c1 == c2


def test_geocode_different_queries_different_coords():
    loc = DemoLocationProvider()
    c1 = loc.geocode("Place A")
    c2 = loc.geocode("Place B")
    assert c1 != c2


def test_route_distance_positive_and_tagged_demo():
    routing = DemoRoutingProvider()
    origin = Coordinates(lat=28.6, lng=77.2)
    dest = Coordinates(lat=28.7, lng=77.3)
    route = routing.get_route(origin, dest)
    assert route.distance_km > 0
    assert route.source == "demo"


def test_route_distance_scales_with_separation():
    routing = DemoRoutingProvider()
    origin = Coordinates(lat=28.6, lng=77.2)
    near = routing.get_route(origin, Coordinates(lat=28.61, lng=77.21))
    far = routing.get_route(origin, Coordinates(lat=29.6, lng=78.2))
    assert far.distance_km > near.distance_km


def test_route_zero_distance_for_same_point():
    routing = DemoRoutingProvider()
    p = Coordinates(lat=28.6, lng=77.2)
    route = routing.get_route(p, p)
    assert route.distance_km == pytest.approx(0.0, abs=1e-6)


def test_stations_nearby_tagged_demo_and_bounded_count():
    stations = DemoChargingStationProvider()
    result = stations.find_nearby(Coordinates(lat=28.6, lng=77.2), radius_km=5, limit=10)
    assert 0 < len(result) <= 10
    assert all(s.source == "demo" for s in result)


def test_stations_nearby_deterministic():
    stations = DemoChargingStationProvider()
    loc = Coordinates(lat=28.6, lng=77.2)
    r1 = stations.find_nearby(loc, radius_km=5)
    r2 = stations.find_nearby(loc, radius_km=5)
    assert [s.station_id for s in r1] == [s.station_id for s in r2]


def test_stations_along_route_uses_route_midpoint():
    routing = DemoRoutingProvider()
    stations = DemoChargingStationProvider()
    route = routing.get_route(Coordinates(lat=28.6, lng=77.2), Coordinates(lat=28.7, lng=77.3))
    result = stations.find_along_route(route, limit=4)
    assert len(result) == 4
    for s in result:
        # stations should cluster near the midpoint (28.65, 77.25), not at origin (0,0)
        assert abs(s.lat - 28.65) < 1.0
        assert abs(s.lng - 77.25) < 1.0


def test_weather_provider_returns_plausible_temperature():
    weather = DemoWeatherProvider()
    result = weather.get_current(Coordinates(lat=28.6, lng=77.2))
    assert 10.0 <= result.temperature_c <= 45.0
    assert result.source == "demo"


# ── Journey energy model ────────────────────────────────────────────────

def _route(distance_km):
    from services.providers.base import RouteResult
    o = Coordinates(lat=0, lng=0)
    d = Coordinates(lat=1, lng=1)
    return RouteResult(distance_km=distance_km, duration_min=distance_km, polyline=None,
                        origin=o, destination=d, source="demo")


def test_feasible_journey_short_trip_high_soc():
    vehicle = VehicleEnergyProfile(battery_capacity_kwh=60.0, efficiency_kwh_per_km=0.15, current_soc_pct=80.0)
    result = estimate_journey_energy(_route(20.0), vehicle)
    assert result.is_feasible_without_charging
    assert result.soc_shortfall_pct == 0.0


def test_infeasible_journey_long_trip_low_soc():
    vehicle = VehicleEnergyProfile(battery_capacity_kwh=40.0, efficiency_kwh_per_km=0.18, current_soc_pct=15.0)
    result = estimate_journey_energy(_route(300.0), vehicle)
    assert not result.is_feasible_without_charging
    assert result.soc_shortfall_pct > 0.0


def test_energy_required_scales_with_distance():
    vehicle = VehicleEnergyProfile(battery_capacity_kwh=60.0, efficiency_kwh_per_km=0.15, current_soc_pct=80.0)
    short = estimate_journey_energy(_route(10.0), vehicle)
    long = estimate_journey_energy(_route(100.0), vehicle)
    assert long.energy_required_kwh > short.energy_required_kwh


def test_traffic_multiplier_increases_energy_required():
    vehicle = VehicleEnergyProfile(battery_capacity_kwh=60.0, efficiency_kwh_per_km=0.15, current_soc_pct=80.0)
    normal = estimate_journey_energy(_route(50.0), vehicle, traffic_multiplier=1.0)
    heavy_traffic = estimate_journey_energy(_route(50.0), vehicle, traffic_multiplier=1.5)
    assert heavy_traffic.energy_required_kwh > normal.energy_required_kwh


def test_elevation_gain_increases_energy_required():
    vehicle = VehicleEnergyProfile(battery_capacity_kwh=60.0, efficiency_kwh_per_km=0.15, current_soc_pct=80.0)
    flat = estimate_journey_energy(_route(50.0), vehicle, elevation_gain_m=0.0)
    hilly = estimate_journey_energy(_route(50.0), vehicle, elevation_gain_m=1000.0)
    assert hilly.energy_required_kwh > flat.energy_required_kwh


def test_required_charge_before_departure_zero_when_already_feasible():
    vehicle = VehicleEnergyProfile(battery_capacity_kwh=60.0, efficiency_kwh_per_km=0.15, current_soc_pct=90.0)
    result = estimate_journey_energy(_route(30.0), vehicle)
    needed = required_charge_before_departure(result, vehicle, target_arrival_buffer_pct=20.0)
    assert needed == 0.0


def test_required_charge_before_departure_positive_when_infeasible():
    vehicle = VehicleEnergyProfile(battery_capacity_kwh=40.0, efficiency_kwh_per_km=0.18, current_soc_pct=15.0)
    result = estimate_journey_energy(_route(300.0), vehicle)
    needed = required_charge_before_departure(result, vehicle, target_arrival_buffer_pct=20.0)
    assert needed > 0.0
    # After charging by exactly this much, the vehicle should just clear the buffer.
    vehicle_after = VehicleEnergyProfile(
        battery_capacity_kwh=40.0, efficiency_kwh_per_km=0.18, current_soc_pct=15.0 + needed)
    result_after = estimate_journey_energy(_route(300.0), vehicle_after)
    assert result_after.expected_arrival_soc_pct >= 19.9  # ~20% buffer, allowing rounding
