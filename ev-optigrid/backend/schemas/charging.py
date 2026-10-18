from pydantic import BaseModel, Field


class OptimizeChargingRequestSchema(BaseModel):
    battery_capacity_kwh: float = Field(..., gt=0)
    max_charge_rate_kw: float = Field(..., gt=0)
    current_soc_pct: float = Field(..., ge=0, le=100)
    target_soc_pct: float = Field(..., ge=0, le=100)
    minimum_safe_soc_pct: float = Field(70.0, ge=0, le=100)
    horizon_slots: int = Field(24, gt=0, le=200)
    slot_minutes: int = Field(15, gt=0, le=120)
    current_price_per_kwh: float = Field(..., ge=0)
    current_grid_load_pct: float = Field(..., ge=0, le=100)
    current_solar_availability_frac: float = Field(0.0, ge=0, le=1)
    profile: str = "balanced"
    custom_weight_overrides: dict | None = None


class ExplanationReasonSchema(BaseModel):
    reason_code: str
    reason_text: str
    supporting_value: float | None = None


class OptimizeChargingResponseSchema(BaseModel):
    result_id: str | None = None   # persisted OptimizationResult id; needed by /charging/explanation
    recommended_action: str
    action_kw: float
    is_feasible: bool
    max_achievable_soc_pct: float
    estimated_cost: float
    immediate_cost: float
    explanation_paragraph: str
    reasons: list[ExplanationReasonSchema]
