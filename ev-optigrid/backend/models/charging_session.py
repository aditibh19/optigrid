import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Float, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from database.session import Base
from models.enums import SessionType


class ChargingSession(Base):
    __tablename__ = "charging_sessions"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    charger_id: Mapped[str] = mapped_column(ForeignKey("chargers.id"), nullable=False)

    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    start_soc: Mapped[float] = mapped_column(Float, nullable=False)
    end_soc: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)

    session_type: Mapped[SessionType] = mapped_column(SAEnum(SessionType), default=SessionType.SIMULATED)

    vehicle = relationship("Vehicle", back_populates="charging_sessions")
    charger = relationship("Charger", back_populates="charging_sessions")

    __table_args__ = (
        Index("ix_sessions_user_start", "user_id", "start_time"),
    )
