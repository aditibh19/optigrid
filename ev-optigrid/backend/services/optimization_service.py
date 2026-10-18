"""
Optimization service (Phase 12, spec §26).

The orchestration layer FastAPI routers call into. Ties together:
  - journey_service (energy requirement, feasibility)
  - optimization/policy.py (cached SDP solve/lookup)
  - optimization/station_optimizer.py (COS ranking)
  - optimization/explainability.py (structured reasons)
  - the DB models (optimization_runs / optimization_results / optimization_explanations)

Kept free of FastAPI-specific types (takes/returns plain dataclasses/dicts)
so it's unit-testable without spinning up the API layer — routers are a
thin translation layer on top of this.
"""
import sys
from pathlib import Path
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for optimization/ and ml/

from optimization.mdp import MDPConfig, bucketize_price, bucketize_grid_load, bucketize_solar
from optimization.reward_model import resolve_weights, real_electricity_cost
from optimization.policy import get_or_solve_policy
from optimization.explainability import DecisionContext, build_explanation, render_explanation_paragraph
from optimization.battery_model import compute_degradation_cost


@dataclass
class OptimizeChargingRequest:
    battery_capacity_kwh: float
    max_charge_rate_kw: float
    current_soc_pct: float
    target_soc_pct: float
    minimum_safe_soc_pct: float
    horizon_slots: int
    slot_minutes: int
    current_price_per_kwh: float
    current_grid_load_pct: float
    current_solar_availability_frac: float
    profile: str = "balanced"
    custom_weight_overrides: dict = None


@dataclass
class OptimizeChargingResult:
    recommended_action: str
    action_kw: float
    is_feasible: bool
    max_achievable_soc_pct: float
    estimated_cost: float
    immediate_cost: float
    explanation_paragraph: str
    reasons: list


def optimize_charging(req: OptimizeChargingRequest) -> OptimizeChargingResult:
    weights = resolve_weights(req.profile, req.custom_weight_overrides)
    config = MDPConfig(
        battery_capacity_kwh=req.battery_capacity_kwh,
        max_charge_rate_kw=req.max_charge_rate_kw,
        slot_minutes=req.slot_minutes,
        horizon_slots=req.horizon_slots,
    )
    policy, _cached = get_or_solve_policy(
        config, weights, target_soc_pct=req.target_soc_pct, minimum_safe_soc_pct=req.minimum_safe_soc_pct,
    )

    price_idx = bucketize_price(req.current_price_per_kwh)
    grid_idx = bucketize_grid_load(req.current_grid_load_pct)
    solar_idx = bucketize_solar(req.current_solar_availability_frac)

    action_kw = policy.action_kw(0, req.current_soc_pct, price_idx, grid_idx, solar_idx)
    recommended_action = "wait" if action_kw <= 0 and req.current_soc_pct < req.target_soc_pct else \
                          ("charge_now" if action_kw > 0 else "no_action_needed")

    # Best achievable SOC at max power for the whole horizon — used for the
    # infeasibility message (spec §13).
    max_config = MDPConfig(battery_capacity_kwh=req.battery_capacity_kwh,
                            max_charge_rate_kw=req.max_charge_rate_kw,
                            slot_minutes=req.slot_minutes, horizon_slots=req.horizon_slots)
    soc = req.current_soc_pct
    for _ in range(req.horizon_slots):
        soc = min(100.0, soc + max_config.soc_gain_pct(req.max_charge_rate_kw))
    max_achievable = soc
    is_feasible = max_achievable >= req.target_soc_pct - 1e-6

    estimated_cost = real_electricity_cost(action_kw, price_idx, config.slot_hours)
    immediate_cost = real_electricity_cost(req.max_charge_rate_kw, price_idx, config.slot_hours)

    degradation = compute_degradation_cost(
        soc_before=req.current_soc_pct, soc_after=min(100.0, req.current_soc_pct + config.soc_gain_pct(action_kw)),
        charge_power_kw=action_kw, max_charge_rate_kw=req.max_charge_rate_kw,
    )

    ctx = DecisionContext(
        recommended_action=recommended_action, action_kw=action_kw,
        current_price_idx=price_idx, current_grid_idx=grid_idx, current_solar_idx=solar_idx,
        current_price_value=req.current_price_per_kwh,
        target_soc_pct=req.target_soc_pct, is_feasible=is_feasible,
        max_achievable_soc_pct=None if is_feasible else round(max_achievable, 1),
        estimated_cost=estimated_cost, immediate_cost=immediate_cost,
        battery_degradation_estimate=degradation,
        renewable_availability_frac=req.current_solar_availability_frac,
    )
    reasons = build_explanation(ctx)
    paragraph = render_explanation_paragraph(reasons)

    return OptimizeChargingResult(
        recommended_action=recommended_action, action_kw=round(action_kw, 2),
        is_feasible=is_feasible, max_achievable_soc_pct=round(max_achievable, 1),
        estimated_cost=round(estimated_cost, 2), immediate_cost=round(immediate_cost, 2),
        explanation_paragraph=paragraph, reasons=[asdict(r) for r in reasons],
    )
