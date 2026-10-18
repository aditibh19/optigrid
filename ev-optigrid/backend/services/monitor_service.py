"""
Condition monitoring for real-time re-optimisation (synopsis workflow: Monitor -> Conditions changed? -> Re-optimise).

`detect_changes` is a pure function: it compares the conditions a plan was made under with the conditions now and
reports which changes are large enough to justify a new plan. Small wobbles are ignored so the plan doesn't flip-flop.
"""
from typing import Any

THRESHOLDS = {
    "price_pct": 15.0,      # electricity price moved by at least 15 %
    "grid_pts": 10.0,       # grid load moved by at least 10 percentage points
    "solar": 0.2,           # solar availability moved by at least 0.2 (of 0..1)
    "queue_min": 10.0,      # expected queue at the station moved by at least 10 minutes
    "deadline_min": 15.0,   # time available to the deadline moved by at least 15 minutes
    "target_pts": 5.0,      # the wanted final charge moved by at least 5 percentage points
}


def _trigger(code: str, label: str, previous: float, current: float, threshold: float, unit: str) -> dict[str, Any]:
    return {"code": code, "label": label, "previous": round(previous, 3), "current": round(current, 3),
            "threshold": threshold, "unit": unit}


def detect_changes(previous, current, previous_queue_wait_min: float | None = None,
                   current_queue_wait_min: float | None = None) -> list[dict[str, Any]]:
    """`previous` / `current` are objects with the OptimizeChargingRequest fields."""
    out: list[dict[str, Any]] = []

    if previous.current_price_per_kwh > 0:
        pct = 100.0 * (current.current_price_per_kwh - previous.current_price_per_kwh) / previous.current_price_per_kwh
        if abs(pct) >= THRESHOLDS["price_pct"]:
            out.append(_trigger("price_change", f"Electricity price {'rose' if pct > 0 else 'fell'} by {abs(pct):.0f}%",
                                previous.current_price_per_kwh, current.current_price_per_kwh, THRESHOLDS["price_pct"], "%"))
    elif current.current_price_per_kwh > 0:
        out.append(_trigger("price_change", "Electricity price is no longer free", 0.0, current.current_price_per_kwh,
                            THRESHOLDS["price_pct"], "%"))

    d_grid = current.current_grid_load_pct - previous.current_grid_load_pct
    if abs(d_grid) >= THRESHOLDS["grid_pts"]:
        out.append(_trigger("grid_change", f"Grid load {'rose' if d_grid > 0 else 'fell'} by {abs(d_grid):.0f} points",
                            previous.current_grid_load_pct, current.current_grid_load_pct, THRESHOLDS["grid_pts"], "points"))

    d_solar = current.current_solar_availability_frac - previous.current_solar_availability_frac
    if abs(d_solar) >= THRESHOLDS["solar"]:
        out.append(_trigger("solar_change", f"Solar availability {'rose' if d_solar > 0 else 'fell'}",
                            previous.current_solar_availability_frac, current.current_solar_availability_frac, THRESHOLDS["solar"], "fraction"))

    if previous_queue_wait_min is not None and current_queue_wait_min is not None:
        d_queue = current_queue_wait_min - previous_queue_wait_min
        if abs(d_queue) >= THRESHOLDS["queue_min"]:
            out.append(_trigger("queue_change", f"Station queue {'grew' if d_queue > 0 else 'shrank'} by {abs(d_queue):.0f} min",
                                previous_queue_wait_min, current_queue_wait_min, THRESHOLDS["queue_min"], "min"))

    d_deadline = (current.horizon_slots * current.slot_minutes) - (previous.horizon_slots * previous.slot_minutes)
    if abs(d_deadline) >= THRESHOLDS["deadline_min"]:
        out.append(_trigger("deadline_change", f"Deadline moved {'later' if d_deadline > 0 else 'earlier'} by {abs(d_deadline) / 60:.1f} h",
                            previous.horizon_slots * previous.slot_minutes, current.horizon_slots * current.slot_minutes,
                            THRESHOLDS["deadline_min"], "min"))

    d_target = current.target_soc_pct - previous.target_soc_pct
    if abs(d_target) >= THRESHOLDS["target_pts"]:
        out.append(_trigger("target_change", f"Wanted charge changed by {abs(d_target):.0f} points",
                            previous.target_soc_pct, current.target_soc_pct, THRESHOLDS["target_pts"], "points"))
    return out
