import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Float, Enum as SAEnum, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from database.session import Base
from models.enums import JourneyStatus, DataSource


class Journey(Base):
    __tablename__ = "journeys"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), nullable=False)

    origin_lat: Mapped[float] = mapped_column(Float, nullable=False)
    origin_lng: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lat: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lng: Mapped[float] = mapped_column(Float, nullable=False)

    departure_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    target_soc: Mapped[float] = mapped_column(Float, default=90.0)

    status: Mapped[JourneyStatus] = mapped_column(SAEnum(JourneyStatus), default=JourneyStatus.PLANNED)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="journeys")
    vehicle = relationship("Vehicle", back_populates="journeys")
    route = relationship("Route", back_populates="journey", uselist=False, cascade="all, delete-orphan")
    optimization_runs = relationship("OptimizationRun", back_populates="journey")

    __table_args__ = (
        Index("ix_journeys_user_created", "user_id", "created_at"),
    )


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    journey_id: Mapped[str] = mapped_column(ForeignKey("journeys.id"), unique=True, nullable=False)

    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    est_duration_min: Mapped[float] = mapped_column(Float, nullable=False)
    est_energy_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    polyline: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[DataSource] = mapped_column(SAEnum(DataSource), default=DataSource.DEMO)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    journey = relationship("Journey", back_populates="route")
