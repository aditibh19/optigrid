import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Float, Boolean, Enum as SAEnum, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from database.session import Base
from models.enums import OptimizationProfile, RecommendedAction


class OptimizationRun(Base):
    """
    One invocation of the optimization pipeline for a journey. A journey can
    have many runs over time — the first plan, plus one new run per
    re-optimization trigger (§12). Never mutated after creation; results are
    always appended, so the full decision history is auditable.
    """
    __tablename__ = "optimization_runs"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    journey_id: Mapped[str | None] = mapped_column(ForeignKey("journeys.id"), nullable=True)
    # nullable: /optimize can be called standalone (no saved Journey) — see api/charging.py
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    # who triggered the run; used to make results/explanations owner-only
    profile_used: Mapped[OptimizationProfile] = mapped_column(SAEnum(OptimizationProfile), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False, default="initial_plan")
    # e.g. "initial_plan","price_change","queue_change","deadline_change","manual_reoptimize"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    journey = relationship("Journey", back_populates="optimization_runs")
    result = relationship("OptimizationResult", back_populates="run", uselist=False,
                           cascade="all, delete-orphan")


class OptimizationResult(Base):
    __tablename__ = "optimization_results"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("optimization_runs.id"), unique=True, nullable=False)

    recommended_action: Mapped[RecommendedAction] = mapped_column(SAEnum(RecommendedAction), nullable=False)
    target_soc: Mapped[float] = mapped_column(Float, nullable=False)
    station_id: Mapped[str | None] = mapped_column(ForeignKey("charging_stations.id"), nullable=True)

    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finish_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    estimated_cost: Mapped[float] = mapped_column(Float, nullable=False)
    immediate_cost_comparison: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)  # 0-1

    is_feasible: Mapped[bool] = mapped_column(Boolean, default=True)
    max_achievable_soc: Mapped[float | None] = mapped_column(Float, nullable=True)  # used in urgent mode

    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    superseded_by_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run = relationship("OptimizationRun", back_populates="result")
    explanations = relationship("OptimizationExplanation", back_populates="result",
                                 cascade="all, delete-orphan")


class OptimizationExplanation(Base):
    """
    Structured reasons behind a result, generated from the same variables the
    optimizer used — never invented text (spec §18). `reason_code` is a
    stable machine key; `reason_text` + `supporting_value` are what's shown
    to the user and what the copilot/LLM is allowed to phrase in prose.
    """
    __tablename__ = "optimization_explanations"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True, default=lambda: str(uuid.uuid4()))
    result_id: Mapped[str] = mapped_column(ForeignKey("optimization_results.id"), nullable=False)

    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g. "electricity_price_advantage","grid_load_advantage","deadline_feasibility",
    # "battery_health_advantage","renewable_availability","queue_advantage"
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    result = relationship("OptimizationResult", back_populates="explanations")

    __table_args__ = (
        Index("ix_explanations_result", "result_id"),
    )
