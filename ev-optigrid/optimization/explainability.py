"""
Explainability engine (Phase 18, spec §18).

Every optimization result must come with structured reasons DERIVED FROM
THE ACTUAL VARIABLES the optimizer used — never invented text. This module
takes the same inputs the SDP/COS pipeline already computed (price/grid/
solar buckets, the COS component scores, feasibility numbers) and produces
a list of `(reason_code, reason_text, supporting_value)` tuples plus one
human-readable paragraph stitched from them.

The AI Copilot (`backend/services/copilot_service.py`) is only allowed to
*rephrase* these reason_text strings in a more conversational tone — it
must not fabricate new reasons or numbers (spec §14).
"""
from dataclasses import dataclass

from optimization.mdp import PRICE_LEVELS, GRID_LEVELS, SOLAR_LEVELS


@dataclass
class ExplanationReason:
    reason_code: str
    reason_text: str
    supporting_value: float | None = None


@dataclass
class DecisionContext:
    """Everything the explainer needs — all values the optimizer actually computed."""
    recommended_action: str          # "charge_now" | "wait" | "charge_partial" | ...
    action_kw: float
    current_price_idx: int
    current_grid_idx: int
    current_solar_idx: int
    predicted_best_price_idx: int | None = None     # bucket at the recommended charging time, if different from now
    predicted_best_time_label: str | None = None    # e.g. "12:15 AM"
    current_price_value: float | None = None        # ₹/kWh, for the "X% lower" phrasing
    predicted_best_price_value: float | None = None
    target_soc_pct: float = 90.0
    is_feasible: bool = True
    max_achievable_soc_pct: float | None = None     # set when infeasible
    finish_time_label: str | None = None
    estimated_cost: float | None = None
    immediate_cost: float | None = None
    battery_degradation_estimate: float | None = None  # from optimization/battery_model.py
    renewable_availability_frac: float | None = None


def build_explanation(ctx: DecisionContext) -> list[ExplanationReason]:
    reasons: list[ExplanationReason] = []

    # Infeasibility takes priority over everything else — the user needs to
    # know the target itself changed before anything about timing (spec §13).
    if not ctx.is_feasible and ctx.max_achievable_soc_pct is not None:
        reasons.append(ExplanationReason(
            reason_code="target_infeasible",
            reason_text=(f"{ctx.target_soc_pct:.0f}% is not achievable before your deadline — "
                         f"the maximum achievable charge is {ctx.max_achievable_soc_pct:.0f}%."),
            supporting_value=ctx.max_achievable_soc_pct,
        ))

    if ctx.recommended_action == "wait" and ctx.predicted_best_price_value is not None and ctx.current_price_value:
        pct_lower = (1 - ctx.predicted_best_price_value / ctx.current_price_value) * 100
        if pct_lower > 1:
            reasons.append(ExplanationReason(
                reason_code="electricity_price_advantage",
                reason_text=(f"Waiting until {ctx.predicted_best_time_label or 'later'} is recommended because "
                             f"the predicted electricity price is {pct_lower:.0f}% lower than right now."),
                supporting_value=round(pct_lower, 1),
            ))

    if ctx.current_grid_idx >= 1 and ctx.recommended_action == "wait":
        reasons.append(ExplanationReason(
            reason_code="grid_load_advantage",
            reason_text=(f"Grid demand is currently {GRID_LEVELS[ctx.current_grid_idx]} and is expected to "
                          f"ease, so charging later reduces strain on the shared grid."),
            supporting_value=float(ctx.current_grid_idx),
        ))

    if ctx.renewable_availability_frac is not None and ctx.renewable_availability_frac > 0.3:
        reasons.append(ExplanationReason(
            reason_code="renewable_availability",
            reason_text=(f"About {ctx.renewable_availability_frac * 100:.0f}% of this charging session "
                          f"could be sourced from solar generation."),
            supporting_value=round(ctx.renewable_availability_frac * 100, 1),
        ))

    if ctx.is_feasible:
        reasons.append(ExplanationReason(
            reason_code="deadline_feasibility",
            reason_text=(f"Your {ctx.target_soc_pct:.0f}% target remains achievable"
                          + (f" before {ctx.finish_time_label}." if ctx.finish_time_label else ".")),
            supporting_value=ctx.target_soc_pct,
        ))

    if ctx.battery_degradation_estimate is not None and ctx.recommended_action in ("wait", "charge_partial"):
        reasons.append(ExplanationReason(
            reason_code="battery_health_advantage",
            reason_text="This charging pattern is gentler on your battery than charging at full power immediately.",
            supporting_value=round(ctx.battery_degradation_estimate, 4),
        ))

    if ctx.estimated_cost is not None and ctx.immediate_cost is not None and ctx.immediate_cost > 0:
        savings = ctx.immediate_cost - ctx.estimated_cost
        if savings > 0.5:
            reasons.append(ExplanationReason(
                reason_code="cost_savings",
                reason_text=f"This plan costs an estimated ₹{ctx.estimated_cost:.0f}, "
                            f"₹{savings:.0f} less than charging immediately (₹{ctx.immediate_cost:.0f}).",
                supporting_value=round(savings, 2),
            ))

    if not reasons:
        # Always return SOMETHING derived from real state, never an empty
        # explanation — falls back to the plain feasibility/price facts.
        reasons.append(ExplanationReason(
            reason_code="default_price_context",
            reason_text=f"Current electricity price is {PRICE_LEVELS[ctx.current_price_idx]} "
                        f"and grid demand is {GRID_LEVELS[ctx.current_grid_idx]}.",
        ))

    return reasons


def render_explanation_paragraph(reasons: list[ExplanationReason]) -> str:
    """Stitches the structured reasons into one readable paragraph — exactly what the
    dashboard's 'Why?' button and the AI Copilot's answer are built from."""
    return " ".join(r.reason_text for r in reasons)
