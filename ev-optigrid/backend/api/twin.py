"""Digital twin endpoint (spec §17): one simulated charging session, slot by slot. Login required."""
from fastapi import APIRouter

from schemas.analysis import TwinRequest
from services import analysis_service as svc

router = APIRouter()


@router.post("/run")
def run_twin(payload: TwinRequest):
    return svc.twin_run(payload)
