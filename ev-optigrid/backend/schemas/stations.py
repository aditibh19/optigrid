from pydantic import BaseModel, Field


class NearbyStationsRequestSchema(BaseModel):
    lat: float
    lng: float
    radius_km: float = Field(5.0, gt=0, le=100)
    limit: int = Field(10, gt=0, le=50)
    profile: str = "balanced"


class ConnectorSchema(BaseModel):
    connector_type: str
    power_kw: float
    price_per_kwh: float
    status: str


class StationCardSchema(BaseModel):
    station_id: str
    name: str
    lat: float
    lng: float
    distance_km: float | None = None
    connectors: list[ConnectorSchema]
    predicted_queue: float | None = None
    predicted_wait_min: float | None = None
    cos_score: float | None = None
    source: str   # "real" | "demo" — always present, never omitted (spec §29)


class JourneyPlanRequestSchema(BaseModel):
    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    vehicle_id: str
    target_soc_pct: float = Field(90.0, ge=0, le=100)
    departure_deadline: str | None = None   # ISO datetime string


class JourneyPlanResponseSchema(BaseModel):
    journey_id: str | None = None   # persisted Journey id; needed by /charging/reoptimize and /schedule
    distance_km: float
    duration_min: float
    energy_required_kwh: float
    expected_arrival_soc_pct: float
    minimum_safe_soc_pct: float
    is_feasible_without_charging: bool
    route_source: str


class CopilotMessageRequestSchema(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    vehicle_id: str | None = None


class CopilotMessageResponseSchema(BaseModel):
    intent: str
    is_valid: bool
    validation_errors: list[str]
    extracted_target_soc_pct: float | None = None
    extracted_deadline: str | None = None
    optimizer_result: dict | None = None
    reply_text: str
