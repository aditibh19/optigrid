import uuid
from datetime import datetime

from sqlalchemy import (String, DateTime, ForeignKey, Float, Boolean, Integer,
                         Enum as SAEnum, Index, JSON)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from database.session import Base
from models.enums import FleetVehicleStatus


def _uuid_pk():
    return mapped_column(PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
                          primary_key=True, default=lambda: str(uuid.uuid4()))


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "reoptimize","urgent_mode","plan_ready"
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")

    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read"),)


class Experiment(Base):
    """A configured What-If Simulator / Research Dashboard run definition (§15, §31)."""
    __tablename__ = "experiments"

    id: Mapped[str] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    # e.g. {"num_evs":50,"num_chargers":10,"grid_capacity_kw":500,"seed":42,...}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    results = relationship("ExperimentResult", back_populates="experiment", cascade="all, delete-orphan")


class ExperimentResult(Base):
    __tablename__ = "experiment_results"

    id: Mapped[str] = _uuid_pk()
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(50), nullable=False)  # greedy/fixed/threshold/priority/sdp

    mean_cost: Mapped[float] = mapped_column(Float, nullable=False)
    std_cost: Mapped[float] = mapped_column(Float, nullable=False)
    mean_wait_min: Mapped[float] = mapped_column(Float, nullable=False)
    peak_load_kw: Mapped[float] = mapped_column(Float, nullable=False)
    soc_violations: Mapped[int] = mapped_column(Integer, default=0)
    deadline_violations: Mapped[int] = mapped_column(Integer, default=0)
    battery_degradation_score: Mapped[float] = mapped_column(Float, default=0.0)
    renewable_utilization_pct: Mapped[float] = mapped_column(Float, default=0.0)
    charger_utilization_pct: Mapped[float] = mapped_column(Float, default=0.0)
    energy_purchased_kwh: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    experiment = relationship("Experiment", back_populates="results")

    __table_args__ = (Index("ix_expresults_experiment_algo", "experiment_id", "algorithm"),)


class FleetVehicle(Base):
    """Runtime state of a vehicle inside a multi-EV fleet simulation/dashboard (§16)."""
    __tablename__ = "fleet_vehicles"

    id: Mapped[str] = _uuid_pk()
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    charger_id: Mapped[str | None] = mapped_column(ForeignKey("chargers.id"), nullable=True)
    status: Mapped[FleetVehicleStatus] = mapped_column(SAEnum(FleetVehicleStatus),
                                                        default=FleetVehicleStatus.WAITING)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    charger = relationship("Charger", back_populates="fleet_assignments")

    __table_args__ = (Index("ix_fleet_status", "status"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_audit_entity", "entity", "entity_id"),)
