"""Fleet charging allocation endpoint (spec §16). Login required."""
from fastapi import APIRouter

from schemas.analysis import FleetRequest
from services import fleet_service

router = APIRouter()


@router.post("/allocate")
def allocate_fleet(payload: FleetRequest):
    return fleet_service.allocate(payload)
