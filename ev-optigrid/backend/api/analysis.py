"""MDP/SDP analysis endpoints for the academic visualisation pages (spec §32). Login required."""
from fastapi import APIRouter, HTTPException, Query

from schemas.analysis import BellmanRequest, HeatmapRequest, MonteCarloRequest, SensitivityRequest
from services import analysis_service as svc

router = APIRouter()


def _bad_request(exc: ValueError):
    raise HTTPException(status_code=422, detail=str(exc))


@router.get("/state-space")
def get_state_space():
    return svc.state_space()


@router.get("/soc-transition")
def get_soc_transition(soc_pct: float = Query(30, ge=0, le=100), action_kw: float = Query(5, ge=0, le=350),
                       battery_capacity_kwh: float = Query(60, gt=0, le=500), slot_minutes: int = Query(15, ge=1, le=120)):
    return svc.soc_transition(soc_pct, action_kw, battery_capacity_kwh, slot_minutes)


@router.post("/policy-heatmap")
def post_policy_heatmap(payload: HeatmapRequest):
    try:
        return svc.policy_heatmap(payload)
    except ValueError as e:
        _bad_request(e)


@router.post("/bellman")
def post_bellman(payload: BellmanRequest):
    try:
        return svc.bellman(payload)
    except ValueError as e:
        _bad_request(e)


@router.post("/monte-carlo")
def post_monte_carlo(payload: MonteCarloRequest):
    try:
        return svc.monte_carlo(payload)
    except ValueError as e:
        _bad_request(e)


@router.post("/sensitivity")
def post_sensitivity(payload: SensitivityRequest):
    return svc.sensitivity(payload)
