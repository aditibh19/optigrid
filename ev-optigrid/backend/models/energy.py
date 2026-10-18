import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Float, Enum as SAEnum, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from database.session import Base
from models.enums import DataSource


class ElectricityPrice(Base):
    __tablename__ = "electricity_prices"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    price_per_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[DataSource] = mapped_column(SAEnum(DataSource), default=DataSource.SIMULATED)

    __table_args__ = (Index("ix_price_region_time", "region", "timestamp"),)


class GridLoad(Base):
    __tablename__ = "grid_load"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    load_pct: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[DataSource] = mapped_column(SAEnum(DataSource), default=DataSource.SIMULATED)

    __table_args__ = (Index("ix_grid_region_time", "region", "timestamp"),)


class SolarGeneration(Base):
    __tablename__ = "solar_generation"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    generation_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[DataSource] = mapped_column(SAEnum(DataSource), default=DataSource.SIMULATED)

    __table_args__ = (Index("ix_solar_region_time", "region", "timestamp"),)


class StationDemand(Base):
    """Historical/live occupancy snapshots used to train the queue predictor."""
    __tablename__ = "station_demand"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    station_id: Mapped[str] = mapped_column(ForeignKey("charging_stations.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    active_sessions: Mapped[int] = mapped_column(Integer, default=0)
    queue_length: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[DataSource] = mapped_column(SAEnum(DataSource), default=DataSource.SIMULATED)

    station = relationship("ChargingStation", back_populates="demand_records")

    __table_args__ = (Index("ix_demand_station_time", "station_id", "timestamp"),)
