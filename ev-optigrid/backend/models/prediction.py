import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Float, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from database.session import Base
from models.enums import PredictionType


class Prediction(Base):
    """
    A single forecast point produced by one of the ml/*_forecaster.py models.
    Kept generic (one table for price/grid/solar/queue/demand) so the
    prediction_service can query/compare across model types uniformly.
    """
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    type: Mapped[PredictionType] = mapped_column(SAEnum(PredictionType), nullable=False)
    region_or_station_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    target_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), default="v1")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_predictions_type_target", "type", "target_time"),
    )
