"""Journey planning endpoints (Phase 12, spec §26)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_owned_vehicle
from database.session import get_db
from models.user import User
from schemas.stations import JourneyPlanRequestSchema, JourneyPlanResponseSchema
from services.journey_service import VehicleEnergyProfile, estimate_journey_energy
from services.providers.factory import get_routing_provider
from services.providers.base import Coordinates
from models.vehicle import Vehicle
from models.journey import Journey, Route

router = APIRouter()


@router.post("", response_model=JourneyPlanResponseSchema)
def plan_journey(payload: JourneyPlanRequestSchema, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    vehicle = get_owned_vehicle(db, user, payload.vehicle_id)

    routing = get_routing_provider()
    route = routing.get_route(
        Coordinates(lat=payload.origin_lat, lng=payload.origin_lng),
        Coordinates(lat=payload.dest_lat, lng=payload.dest_lng),
    )

    profile = VehicleEnergyProfile(
        battery_capacity_kwh=vehicle.battery_capacity_kwh,
        efficiency_kwh_per_km=vehicle.efficiency_kwh_per_km,
        current_soc_pct=vehicle.current_soc,
    )
    energy_result = estimate_journey_energy(route, profile)

    journey = Journey(
        user_id=user.id, vehicle_id=vehicle.id,
        origin_lat=payload.origin_lat, origin_lng=payload.origin_lng,
        dest_lat=payload.dest_lat, dest_lng=payload.dest_lng,
        target_soc=payload.target_soc_pct,
    )
    db.add(journey)
    db.flush()
    db.add(Route(journey_id=journey.id, distance_km=route.distance_km, est_duration_min=route.duration_min,
                  est_energy_kwh=energy_result.energy_required_kwh, source=route.source))
    db.commit()

    return JourneyPlanResponseSchema(
        journey_id=journey.id, distance_km=route.distance_km, duration_min=route.duration_min,
        energy_required_kwh=energy_result.energy_required_kwh,
        expected_arrival_soc_pct=energy_result.expected_arrival_soc_pct,
        minimum_safe_soc_pct=energy_result.minimum_safe_soc_pct,
        is_feasible_without_charging=energy_result.is_feasible_without_charging,
        route_source=route.source,
    )
