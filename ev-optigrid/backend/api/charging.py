"""
Charging optimization endpoints (Phase 12, spec §26).

POST /api/charging/optimize     — initial plan
POST /api/charging/reoptimize   — re-run after a detected change (spec §12)
GET  /api/charging/schedule     — latest result for a journey
GET  /api/charging/explanation  — structured reasons for a result

Thin translation layer: validates via the Pydantic schema, calls
services.optimization_service, persists via the DB models, returns the
schema response. No optimization logic lives here.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_owned_journey
from database.session import get_db
from models.user import User
from schemas.charging import OptimizeChargingRequestSchema, OptimizeChargingResponseSchema
from services.optimization_service import OptimizeChargingRequest, optimize_charging
from models.optimization import OptimizationRun, OptimizationResult, OptimizationExplanation
from models.enums import RecommendedAction, OptimizationProfile
from services import monitor_service

router = APIRouter()


def _to_service_request(schema: OptimizeChargingRequestSchema) -> OptimizeChargingRequest:
    return OptimizeChargingRequest(**schema.model_dump())


def _to_profile_enum(value: str) -> OptimizationProfile:
    """The API takes the profile as a string; the DB column is an Enum."""
    try:
        return OptimizationProfile(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown profile '{value}'. "
                            f"Valid: {[p.value for p in OptimizationProfile]}")


@router.post("/optimize", response_model=OptimizeChargingResponseSchema)
def optimize(payload: OptimizeChargingRequestSchema, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    result = optimize_charging(_to_service_request(payload))

    # Persist the run/result/explanations (append-only — see docs/DATABASE.md).
    # journey_id is omitted here since this endpoint can be called standalone
    # (e.g. from the Smart Charging page without a saved Journey); the
    # journey-linked variant is reoptimize(), below, which requires one.
    run = OptimizationRun(journey_id=None, user_id=user.id, profile_used=_to_profile_enum(payload.profile),
                          triggered_by="initial_plan")
    db.add(run)
    db.flush()

    action_enum = {
        "wait": RecommendedAction.WAIT, "charge_now": RecommendedAction.CHARGE_NOW,
    }.get(result.recommended_action, RecommendedAction.CHARGE_PARTIAL)

    db_result = OptimizationResult(
        run_id=run.id, recommended_action=action_enum, target_soc=payload.target_soc_pct,
        estimated_cost=result.estimated_cost, immediate_cost_comparison=result.immediate_cost,
        is_feasible=result.is_feasible, max_achievable_soc=result.max_achievable_soc_pct,
    )
    db.add(db_result)
    db.flush()

    for reason in result.reasons:
        db.add(OptimizationExplanation(result_id=db_result.id, **reason))

    db.commit()
    return OptimizeChargingResponseSchema(**result.__dict__, result_id=db_result.id)


@router.post("/reoptimize", response_model=OptimizeChargingResponseSchema)
def reoptimize(payload: OptimizeChargingRequestSchema, journey_id: str,
               triggered_by: str = "manual_reoptimize", db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """
    Spec §12: re-optimization always creates a NEW run rather than editing
    the previous result, and marks the previous result stale/superseded so
    old-vs-new comparisons are a simple query.
    """
    get_owned_journey(db, user, journey_id)   # 404 if unknown or someone else's
    previous = (
        db.query(OptimizationResult)
        .join(OptimizationRun)
        .filter(OptimizationRun.journey_id == journey_id)
        .order_by(OptimizationResult.created_at.desc())
        .first()
    )

    result = optimize_charging(_to_service_request(payload))

    run = OptimizationRun(journey_id=journey_id, user_id=user.id, profile_used=_to_profile_enum(payload.profile),
                          triggered_by=triggered_by)
    db.add(run)
    db.flush()

    action_enum = {
        "wait": RecommendedAction.WAIT, "charge_now": RecommendedAction.CHARGE_NOW,
    }.get(result.recommended_action, RecommendedAction.CHARGE_PARTIAL)

    db_result = OptimizationResult(
        run_id=run.id, recommended_action=action_enum, target_soc=payload.target_soc_pct,
        estimated_cost=result.estimated_cost, immediate_cost_comparison=result.immediate_cost,
        is_feasible=result.is_feasible, max_achievable_soc=result.max_achievable_soc_pct,
    )
    db.add(db_result)
    db.flush()

    if previous:
        previous.is_stale = True
        previous.superseded_by_run_id = run.id

    for reason in result.reasons:
        db.add(OptimizationExplanation(result_id=db_result.id, **reason))

    db.commit()
    return OptimizeChargingResponseSchema(**result.__dict__, result_id=db_result.id)


@router.get("/schedule")
def get_latest_schedule(journey_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_owned_journey(db, user, journey_id)
    result = (
        db.query(OptimizationResult)
        .join(OptimizationRun)
        .filter(OptimizationRun.journey_id == journey_id, OptimizationResult.is_stale == False)  # noqa: E712
        .order_by(OptimizationResult.created_at.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="No optimization result found for this journey.")
    return {
        "result_id": result.id, "recommended_action": result.recommended_action.value, "target_soc": result.target_soc,
        "estimated_cost": result.estimated_cost, "is_feasible": result.is_feasible,
        "max_achievable_soc": result.max_achievable_soc,
    }


@router.get("/explanation")
def get_explanation(result_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    owner_id = (db.query(OptimizationRun.user_id).join(OptimizationResult, OptimizationResult.run_id == OptimizationRun.id)
                .filter(OptimizationResult.id == result_id).scalar())
    if owner_id != user.id:
        raise HTTPException(status_code=404, detail="No explanation found for this result.")
    explanations = db.query(OptimizationExplanation).filter_by(result_id=result_id).all()
    if not explanations:
        raise HTTPException(status_code=404, detail="No explanation found for this result.")
    return {"reasons": [{"reason_code": e.reason_code, "reason_text": e.reason_text,
                          "supporting_value": e.supporting_value} for e in explanations]}


class MonitorRequest(BaseModel):
    previous: OptimizeChargingRequestSchema      # conditions the current plan was made under
    current: OptimizeChargingRequestSchema       # conditions now
    previous_queue_wait_min: float | None = Field(None, ge=0)
    current_queue_wait_min: float | None = Field(None, ge=0)
    journey_id: str | None = None                # when given, a new plan is stored against this journey


@router.get("/monitor/thresholds")
def monitor_thresholds():
    """How large a change must be before the plan is recomputed."""
    return monitor_service.THRESHOLDS


@router.post("/monitor")
def monitor(payload: MonitorRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    One pass of the monitoring loop (synopsis workflow: Monitor -> Conditions changed? -> Re-optimise).

    Compares the conditions the plan was made under with the conditions now. If something material changed
    (see /monitor/thresholds) a NEW plan is computed and stored, and the old one is marked stale when a journey
    is given (append-only history, spec §12). If nothing material changed, the plan is left alone.
    Both plans are returned so the client can show a before/after comparison.
    """
    if payload.journey_id:
        get_owned_journey(db, user, payload.journey_id)

    triggers = monitor_service.detect_changes(payload.previous, payload.current,
                                               payload.previous_queue_wait_min, payload.current_queue_wait_min)
    before = optimize_charging(_to_service_request(payload.previous))

    if triggers:
        codes = ",".join(t["code"] for t in triggers)
        if payload.journey_id:
            after_schema = reoptimize(payload.current, payload.journey_id, triggered_by=codes, db=db, user=user)
        else:
            after_schema = optimize(payload.current, db=db, user=user)
    else:
        after_schema = OptimizeChargingResponseSchema(**optimize_charging(_to_service_request(payload.current)).__dict__)

    return {"changed": bool(triggers), "triggers": triggers, "thresholds": monitor_service.THRESHOLDS,
            "action_changed": before.recommended_action != after_schema.recommended_action,
            "reoptimized": bool(triggers), "stored": bool(triggers),
            "previous": OptimizeChargingResponseSchema(**before.__dict__),
            "current": after_schema}
