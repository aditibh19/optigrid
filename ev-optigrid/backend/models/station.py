import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Float, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from database.session import Base
from models.enums import DataSource, ConnectorType, ChargerStatus


class ChargingStation(Base):
    __tablename__ = "charging_stations"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    source: Mapped[DataSource] = mapped_column(SAEnum(DataSource), default=DataSource.DEMO)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    chargers = relationship("Charger", back_populates="station", cascade="all, delete-orphan")
    demand_records = relationship("StationDemand", back_populates="station")

    __table_args__ = (
        Index("ix_stations_lat_lng", "lat", "lng"),
    )


class Charger(Base):
    __tablename__ = "chargers"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    station_id: Mapped[str] = mapped_column(ForeignKey("charging_stations.id"), nullable=False)

    connector_type: Mapped[ConnectorType] = mapped_column(SAEnum(ConnectorType), nullable=False)
    power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    price_per_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[ChargerStatus] = mapped_column(SAEnum(ChargerStatus), default=ChargerStatus.AVAILABLE)

    station = relationship("ChargingStation", back_populates="chargers")
    charging_sessions = relationship("ChargingSession", back_populates="charger")
    fleet_assignments = relationship("FleetVehicle", back_populates="charger")

    __table_args__ = (
        Index("ix_chargers_station_status", "station_id", "status"),
    )
