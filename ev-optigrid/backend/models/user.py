import uuid
from datetime import datetime, time

from sqlalchemy import String, DateTime, ForeignKey, Float, Integer, Time, Boolean, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from database.session import Base
from models.enums import OptimizationProfile


def _uuid_col():
    return mapped_column(PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
                          primary_key=True, default=lambda: str(uuid.uuid4()))


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = _uuid_col()
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    vehicles = relationship("Vehicle", back_populates="owner", cascade="all, delete-orphan")
    preferences = relationship("UserPreference", back_populates="user", uselist=False,
                                cascade="all, delete-orphan")
    journeys = relationship("Journey", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")


class UserPreference(Base):
    """
    Explicit personalization inputs (spec §8). Learned historical behaviour
    (e.g. usual departure time) is stored separately as a *soft* signal and
    must never override these explicit values — enforced in
    services/optimization_service.py, not at the DB layer.
    """
    __tablename__ = "user_preferences"

    id: Mapped[str] = _uuid_col()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)

    profile: Mapped[OptimizationProfile] = mapped_column(
        SAEnum(OptimizationProfile), default=OptimizationProfile.BALANCED)

    target_soc_default: Mapped[float] = mapped_column(Float, default=90.0)
    preferred_departure_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    cost_sensitivity: Mapped[float] = mapped_column(Float, default=0.5)       # 0-1
    battery_health_sensitivity: Mapped[float] = mapped_column(Float, default=0.5)
    renewable_preference: Mapped[float] = mapped_column(Float, default=0.5)
    max_acceptable_wait_min: Mapped[int] = mapped_column(Integer, default=20)
    fast_charging_preference: Mapped[float] = mapped_column(Float, default=0.5)

    # Custom weight overrides (used when profile == CUSTOM); nullable so the
    # profile-derived defaults apply otherwise.
    custom_w_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    custom_w_battery: Mapped[float | None] = mapped_column(Float, nullable=True)
    custom_w_grid: Mapped[float | None] = mapped_column(Float, nullable=True)
    custom_w_wait: Mapped[float | None] = mapped_column(Float, nullable=True)
    custom_w_travel: Mapped[float | None] = mapped_column(Float, nullable=True)
    custom_w_unmet: Mapped[float | None] = mapped_column(Float, nullable=True)
    custom_w_deadline: Mapped[float | None] = mapped_column(Float, nullable=True)
    custom_w_renewable: Mapped[float | None] = mapped_column(Float, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                  onupdate=datetime.utcnow)

    user = relationship("User", back_populates="preferences")
