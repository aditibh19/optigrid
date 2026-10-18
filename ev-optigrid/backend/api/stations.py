"""Nearby/route station discovery endpoints (Phase 12, spec §26)."""
from fastapi import APIRouter

from schemas.stations import NearbyStationsRequestSchema, StationCardSchema
from services.station_service import get_ranked_nearby_stations

router = APIRouter()


@router.get("/nearby", response_model=list[StationCardSchema])
def nearby_stations(lat: float, lng: float, radius_km: float = 5.0, limit: int = 10,
                     profile: str = "balanced", vehicle_max_charge_rate_kw: float = 50.0,
                     target_soc_pct: float = 90.0, current_soc_pct: float = 50.0):
    stations = get_ranked_nearby_stations(
        location_lat=lat, location_lng=lng, radius_km=radius_km, limit=limit, profile=profile,
        vehicle_max_charge_rate_kw=vehicle_max_charge_rate_kw, target_soc_pct=target_soc_pct,
        current_soc_pct=current_soc_pct,
    )
    return stations


@router.get("/route")
def stations_along_route(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float,
                          corridor_km: float = 2.0, limit: int = 10, profile: str = "balanced"):
    from services.providers.factory import get_routing_provider, get_station_provider
    from services.providers.base import Coordinates

    routing = get_routing_provider()
    stations_provider = get_station_provider()
    route = routing.get_route(Coordinates(lat=origin_lat, lng=origin_lng), Coordinates(lat=dest_lat, lng=dest_lng))
    stations = stations_provider.find_along_route(route, corridor_km=corridor_km, limit=limit)
    return {"route": {"distance_km": route.distance_km, "duration_min": route.duration_min, "source": route.source},
            "stations": [{"station_id": s.station_id, "name": s.name, "lat": s.lat, "lng": s.lng,
                           "source": s.source} for s in stations]}
