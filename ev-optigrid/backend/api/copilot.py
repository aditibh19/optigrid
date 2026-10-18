"""AI Copilot endpoint (Phase 12/15, spec §14/§26)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_owned_vehicle
from database.session import get_db
from models.user import User

from schemas.stations import CopilotMessageRequestSchema, CopilotMessageResponseSchema
from services.copilot_service import handle_message
from services.optimization_service import OptimizeChargingRequest, optimize_charging

router = APIRouter()


def _default_optimizer_callback(vehicle_defaults: dict):
    """
    Builds the optimizer_callback handle_message() expects, pre-filling
    live grid/price context and the vehicle's own specs so the copilot's
    extracted parameters (target SOC / deadline) are the only things it
    needs to layer on top — the SDP still makes the actual decision (spec
    §14: "The LLM MUST NOT invent the charging schedule").
    """
    def _callback(extracted):
        target_soc = extracted.target_soc_pct or vehicle_defaults.get("target_soc_pct", 90.0)
        req = OptimizeChargingRequest(
            battery_capacity_kwh=vehicle_defaults["battery_capacity_kwh"],
            max_charge_rate_kw=vehicle_defaults["max_charge_rate_kw"],
            current_soc_pct=vehicle_defaults["current_soc_pct"],
            target_soc_pct=target_soc,
            minimum_safe_soc_pct=target_soc * 0.8,
            horizon_slots=vehicle_defaults.get("horizon_slots", 24),
            slot_minutes=vehicle_defaults.get("slot_minutes", 15),
            current_price_per_kwh=vehicle_defaults["current_price_per_kwh"],
            current_grid_load_pct=vehicle_defaults["current_grid_load_pct"],
            current_solar_availability_frac=vehicle_defaults.get("current_solar_availability_frac", 0.0),
        )
        result = optimize_charging(req)
        return {"recommended_action": result.recommended_action, "action_kw": result.action_kw,
                "is_feasible": result.is_feasible, "max_achievable_soc_pct": result.max_achievable_soc_pct,
                "explanation_paragraph": result.explanation_paragraph}
    return _callback


@router.post("/parse", response_model=CopilotMessageResponseSchema)
def parse_copilot_message(payload: CopilotMessageRequestSchema, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    # Illustrative defaults when no vehicle is given; a supplied vehicle_id must be
    # the caller's own, and then its real specs and charge level are used.
    vehicle_defaults = {
        "battery_capacity_kwh": 60.0, "max_charge_rate_kw": 50.0, "current_soc_pct": 40.0,
        "target_soc_pct": 90.0, "current_price_per_kwh": 8.0, "current_grid_load_pct": 60.0,
    }
    if payload.vehicle_id:
        vehicle = get_owned_vehicle(db, user, payload.vehicle_id)
        vehicle_defaults.update(battery_capacity_kwh=vehicle.battery_capacity_kwh,
                                max_charge_rate_kw=vehicle.max_charge_rate_kw,
                                current_soc_pct=vehicle.current_soc)
    response = handle_message(payload.message, optimizer_callback=_default_optimizer_callback(vehicle_defaults))

    reply_text = response.explanation_text
    if reply_text is None:
        if not response.validation.is_valid:
            reply_text = "I need a bit more detail — " + "; ".join(response.validation.errors)
        elif response.intent == "find_charger":
            reply_text = "Here are the nearby charging stations ranked for your preferences."
        else:
            reply_text = "Got it — let me know if you'd like me to plan a charging schedule."

    return CopilotMessageResponseSchema(
        intent=response.intent, is_valid=response.validation.is_valid,
        validation_errors=response.validation.errors,
        extracted_target_soc_pct=response.extracted.target_soc_pct,
        extracted_deadline=str(response.extracted.deadline_time) if response.extracted.deadline_time else None,
        optimizer_result=response.optimizer_result, reply_text=reply_text,
    )
