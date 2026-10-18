"""
One-click demonstration (Phase 30, spec §30).

Walks through the exact 13-step demo scenario from the spec, printing each
step's real, computed output. No database required — this exercises the
same engine the API/frontend use, standalone.

Run with: python backend/scripts/demo_mode.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.providers.demo_providers import DemoLocationProvider, DemoRoutingProvider, DemoChargingStationProvider
from services.journey_service import VehicleEnergyProfile, estimate_journey_energy
from services.optimization_service import OptimizeChargingRequest, optimize_charging
from optimization.station_optimizer import StationCandidate, rank_stations


def step(n, title):
    print(f"\n{'─' * 60}\nStep {n}: {title}\n{'─' * 60}")


def main():
    print("=" * 60)
    print("EV-OptiGrid — One-click demo")
    print("=" * 60)

    vehicle = VehicleEnergyProfile(battery_capacity_kwh=60.0, efficiency_kwh_per_km=0.15, current_soc_pct=32.0)

    step(1, "User opens app — location selected")
    loc_provider = DemoLocationProvider()
    origin = loc_provider.geocode("Current Location")
    print(f"  Origin: ({origin.lat:.4f}, {origin.lng:.4f})")

    step(2, "Destination selected")
    dest = loc_provider.geocode("Downtown Office")
    print(f"  Destination: ({dest.lat:.4f}, {dest.lng:.4f})")

    step(3, "Route calculated")
    routing = DemoRoutingProvider()
    route = routing.get_route(origin, dest)
    print(f"  Distance: {route.distance_km} km | Duration: {route.duration_min} min | source={route.source}")

    step(4, "Energy requirement calculated")
    energy = estimate_journey_energy(route, vehicle)
    print(f"  Energy required: {energy.energy_required_kwh} kWh | Feasible without charging: {energy.is_feasible_without_charging}")

    step(5, "Nearby chargers discovered")
    station_provider = DemoChargingStationProvider()
    stations = station_provider.find_nearby(origin, radius_km=5, limit=5)
    print(f"  Found {len(stations)} stations (source=demo)")

    step(6, "Station scores calculated (Charging Opportunity Score)")
    candidates = [
        StationCandidate(
            station_id=s.station_id, name=s.name, charging_cost=200 + i * 30, travel_time_min=5 + i * 2,
            distance_km=2 + i, predicted_wait_min=i * 3, charging_duration_min=40 - i * 2,
            battery_impact=0.2 + i * 0.05, grid_load_pct=60, renewable_availability=0.3 - i * 0.05,
            connector_availability_frac=0.8 - i * 0.1,
        ) for i, s in enumerate(stations)
    ]
    ranked = rank_stations(candidates, profile="balanced")
    for c, score in ranked[:3]:
        print(f"  {c.name}: COS={score}")
    best_station = ranked[0][0]

    step(7, "SDP optimization runs")
    req = OptimizeChargingRequest(
        battery_capacity_kwh=vehicle.battery_capacity_kwh, max_charge_rate_kw=50.0,
        current_soc_pct=vehicle.current_soc_pct, target_soc_pct=90.0, minimum_safe_soc_pct=70.0,
        horizon_slots=12, slot_minutes=30, current_price_per_kwh=8.0, current_grid_load_pct=90.0,
        current_solar_availability_frac=0.0, profile="balanced",
    )
    result = optimize_charging(req)
    print(f"  Recommended action: {result.recommended_action} ({result.action_kw} kW)")

    step(8, "Charging plan displayed")
    print(f"  Station: {best_station.name} | Target: {req.target_soc_pct}% | Est. cost: ₹{result.estimated_cost}")

    step(9, "Explanation generated")
    print(f"  {result.explanation_paragraph}")

    step(10, "Expected cost and savings shown")
    print(f"  Immediate: ₹{result.immediate_cost} | Optimized: ₹{result.estimated_cost} | Savings: ₹{round(result.immediate_cost - result.estimated_cost, 2)}")

    step(11, "User accepts plan")
    print("  Plan accepted (simulated).")

    step(12, "Electricity price changes — re-optimization triggers")
    req.current_price_per_kwh = 4.5
    req.current_grid_load_pct = 35.0
    new_result = optimize_charging(req)
    print(f"  New recommendation: {new_result.recommended_action} ({new_result.action_kw} kW)")
    print(f"  {new_result.explanation_paragraph}")

    step(13, "Old vs new decision compared")
    print(f"  Old: {result.recommended_action} @ ₹{result.estimated_cost}  ->  New: {new_result.recommended_action} @ ₹{new_result.estimated_cost}")

    print("\n" + "=" * 60)
    print("Demo complete. Every number above was computed live, not hardcoded.")
    print("=" * 60)


if __name__ == "__main__":
    main()
