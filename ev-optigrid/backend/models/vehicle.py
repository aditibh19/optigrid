import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from database.session import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    make: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))

    battery_capacity_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    efficiency_kwh_per_km: Mapped[float] = mapped_column(Float, nullable=False)
    max_charge_rate_kw: Mapped[float] = mapped_column(Float, nullable=False)

    current_soc: Mapped[float] = mapped_column(Float, default=50.0)     # %
    battery_health_pct: Mapped[float] = mapped_column(Float, default=100.0)  # simulated indicator

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="vehicles")
    journeys = relationship("Journey", back_populates="vehicle")
    charging_sessions = relationship("ChargingSession", back_populates="vehicle")
