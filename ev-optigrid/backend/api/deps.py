"""
Shared FastAPI dependencies: authentication and ownership checks (spec §34).

Public endpoints (no token): /health*, /api/auth/*, /api/predictions/*,
/api/stations/* (market data, nothing personal).
Everything else requires `Authorization: Bearer <access token>`, and anything
that belongs to a user (vehicles, journeys, optimisation results) is only
visible to its owner — other users get a 404, not a 403, so ids can't be probed.
"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from database.session import get_db
from models.journey import Journey
from models.user import User
from models.vehicle import Vehicle
from services.auth_service import decode_token

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def user_from_token(token: str, expected_type: str, db: Session) -> User:
    """Validates signature + expiry + token type ('access' or 'refresh') and loads the user."""
    try:
        payload = decode_token(token)
    except JWTError:
        raise _unauthorized("Invalid or expired token.")
    if payload.get("type") != expected_type:
        # e.g. a refresh token presented as an access token
        raise _unauthorized(f"Wrong token type: expected a {expected_type} token.")
    subject = payload.get("sub")
    user = db.get(User, subject) if subject else None
    if user is None:
        raise _unauthorized("The account for this token no longer exists.")
    return user


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
                     db: Session = Depends(get_db)) -> User:
    if credentials is None:
        raise _unauthorized("Not authenticated. Log in and send 'Authorization: Bearer <access token>'.")
    return user_from_token(credentials.credentials, "access", db)


def get_owned_vehicle(db: Session, user: User, vehicle_id: str) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.user_id != user.id:
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    return vehicle


def get_owned_journey(db: Session, user: User, journey_id: str) -> Journey:
    journey = db.get(Journey, journey_id)
    if journey is None or journey.user_id != user.id:
        raise HTTPException(status_code=404, detail="Journey not found.")
    return journey
