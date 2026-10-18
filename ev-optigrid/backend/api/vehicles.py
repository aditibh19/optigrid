"""Vehicle CRUD endpoints (spec §26). All routes require login and are owner-only."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from api.deps import get_current_user, get_owned_vehicle
from database.session import get_db
from models.user import User
from models.vehicle import Vehicle

router = APIRouter()


class VehicleCreateRequest(BaseModel):
    user_id: str | None = None   # optional and ignored: the owner is always the logged-in user
    make: str
    model: str
    battery_capacity_kwh: float = Field(..., gt=0)
    efficiency_kwh_per_km: float = Field(..., gt=0)
    max_charge_rate_kw: float = Field(..., gt=0)
    current_soc: float = Field(50.0, ge=0, le=100)


class VehicleResponse(BaseModel):
    id: str
    make: str
    model: str
    battery_capacity_kwh: float
    efficiency_kwh_per_km: float
    max_charge_rate_kw: float
    current_soc: float
    battery_health_pct: float

    class Config:
        from_attributes = True


def _reject_other_users(user_id: str | None, user: User) -> None:
    if user_id is not None and user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only manage your own vehicles.")


@router.post("", response_model=VehicleResponse, status_code=201)
def create_vehicle(payload: VehicleCreateRequest, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    _reject_other_users(payload.user_id, user)
    data = payload.model_dump(exclude={"user_id"})
    vehicle = Vehicle(user_id=user.id, **data)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.get("", response_model=list[VehicleResponse])
def list_vehicles(user_id: str | None = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    _reject_other_users(user_id, user)
    return db.query(Vehicle).filter(Vehicle.user_id == user.id).all()


@router.get("/{vehicle_id}", response_model=VehicleResponse)
def get_vehicle(vehicle_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_owned_vehicle(db, user, vehicle_id)
