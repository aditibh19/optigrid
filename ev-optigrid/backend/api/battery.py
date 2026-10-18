"""Battery degradation model curves (spec §9). Login required."""
from fastapi import APIRouter, Query

from services import analysis_service as svc

router = APIRouter()


@router.get("/curves")
def battery_curves(max_charge_rate_kw: float = Query(50, gt=0, le=350), ambient_temp_c: float | None = Query(25, ge=-40, le=60)):
    return svc.battery_curves(max_charge_rate_kw, ambient_temp_c)
