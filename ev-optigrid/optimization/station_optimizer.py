"""
Charging Opportunity Score (COS) — Phase 9, spec §4.

COS = w_cost*cost_score + w_time*time_score + w_queue*queue_score
    + w_distance*distance_score + w_battery*battery_score + w_grid*grid_score
    + w_renewable*renewable_score + w_availability*availability_score

scaled to 0-100. Weights are user-preference-dependent (§4: "Allow weights
to depend on user preference") via the same six profiles as the SDP
(save_money / fastest / battery_health / green / balanced / custom), so
switching profile changes which station comes out on top, not just how the
charging RATE decision goes.

Normalization approach (spec §4: "Normalize the components. Do NOT hardcode
scores. Calculate them from actual data."): each raw attribute is min-max
normalized ACROSS the current candidate set — i.e. "distance_score" answers
"how good is this station's distance relative to the other candidates being
compared right now", not against some arbitrary global constant. This is
the right normalization for a ranking metric (its job is to order a
specific candidate list) and sidesteps having to pick defensible absolute
bounds for every raw unit (₹, km, minutes, %). When every candidate is
identical on some attribute (all-equal edge case), that attribute
contributes full marks to everyone rather than dividing by zero.
"""
from dataclasses import dataclass


@dataclass
class StationCandidate:
    """Raw, unnormalized data for one candidate charging station."""
    station_id: str
    name: str
    charging_cost: float          # ₹ for the planned session at this station
    travel_time_min: float        # time to reach the station (incl. driving)
    distance_km: float
    predicted_wait_min: float
    charging_duration_min: float  # time to reach target SOC once charging starts
    battery_impact: float         # degradation cost estimate for this session (0-1ish, from battery_model)
    grid_load_pct: float          # current/predicted grid load at the time of charging
    renewable_availability: float  # 0-1: fraction of session that could be solar-sourced
    connector_availability_frac: float  # available_connectors / total_connectors, 0-1


@dataclass
class COSWeights:
    w_cost: float
    w_time: float
    w_queue: float
    w_distance: float
    w_battery: float
    w_grid: float
    w_renewable: float
    w_availability: float


COS_PROFILE_WEIGHTS: dict[str, COSWeights] = {
    "save_money":     COSWeights(w_cost=3.0, w_time=0.5, w_queue=0.5, w_distance=0.5, w_battery=0.5, w_grid=0.5, w_renewable=0.5, w_availability=0.5),
    "fastest":        COSWeights(w_cost=0.3, w_time=3.0, w_queue=2.0, w_distance=2.0, w_battery=0.2, w_grid=0.2, w_renewable=0.2, w_availability=1.5),
    "battery_health": COSWeights(w_cost=0.5, w_time=0.5, w_queue=0.5, w_distance=0.5, w_battery=3.0, w_grid=0.5, w_renewable=0.5, w_availability=0.5),
    "green":          COSWeights(w_cost=0.5, w_time=0.5, w_queue=0.5, w_distance=0.5, w_battery=0.5, w_grid=0.5, w_renewable=3.0, w_availability=0.5),
    "balanced":       COSWeights(w_cost=1.0, w_time=1.0, w_queue=1.0, w_distance=1.0, w_battery=1.0, w_grid=1.0, w_renewable=1.0, w_availability=1.0),
    "custom":         COSWeights(w_cost=1.0, w_time=1.0, w_queue=1.0, w_distance=1.0, w_battery=1.0, w_grid=1.0, w_renewable=1.0, w_availability=1.0),
}


def resolve_cos_weights(profile: str, custom_overrides: dict | None = None) -> COSWeights:
    base = COS_PROFILE_WEIGHTS.get(profile, COS_PROFILE_WEIGHTS["balanced"])
    if profile != "custom" or not custom_overrides:
        return base
    merged = {**base.__dict__, **{k: v for k, v in custom_overrides.items() if v is not None}}
    return COSWeights(**merged)


def _minmax_goodness(values: list[float], higher_is_better: bool) -> list[float]:
    """Normalizes a list of raw values to [0,1] "goodness" scores, relative to each other."""
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [1.0] * len(values)  # no differentiation possible — don't penalize anyone
    if higher_is_better:
        return [(v - lo) / (hi - lo) for v in values]
    return [(hi - v) / (hi - lo) for v in values]


def compute_cos_scores(candidates: list[StationCandidate], weights: COSWeights) -> dict[str, float]:
    """
    Returns {station_id: COS} for every candidate, scaled to 0-100.
    Computed relative to THIS candidate set — re-run whenever the candidate
    list changes (new stations discovered, a station drops out).
    """
    if not candidates:
        return {}

    cost_goodness = _minmax_goodness([c.charging_cost for c in candidates], higher_is_better=False)
    time_goodness = _minmax_goodness([c.travel_time_min + c.charging_duration_min for c in candidates], higher_is_better=False)
    queue_goodness = _minmax_goodness([c.predicted_wait_min for c in candidates], higher_is_better=False)
    distance_goodness = _minmax_goodness([c.distance_km for c in candidates], higher_is_better=False)
    battery_goodness = _minmax_goodness([c.battery_impact for c in candidates], higher_is_better=False)
    grid_goodness = _minmax_goodness([c.grid_load_pct for c in candidates], higher_is_better=False)
    renewable_goodness = _minmax_goodness([c.renewable_availability for c in candidates], higher_is_better=True)
    availability_goodness = _minmax_goodness([c.connector_availability_frac for c in candidates], higher_is_better=True)

    total_weight = (weights.w_cost + weights.w_time + weights.w_queue + weights.w_distance
                    + weights.w_battery + weights.w_grid + weights.w_renewable + weights.w_availability)

    scores = {}
    for i, c in enumerate(candidates):
        weighted_sum = (
            weights.w_cost * cost_goodness[i]
            + weights.w_time * time_goodness[i]
            + weights.w_queue * queue_goodness[i]
            + weights.w_distance * distance_goodness[i]
            + weights.w_battery * battery_goodness[i]
            + weights.w_grid * grid_goodness[i]
            + weights.w_renewable * renewable_goodness[i]
            + weights.w_availability * availability_goodness[i]
        )
        scores[c.station_id] = round(100.0 * weighted_sum / total_weight, 1)
    return scores


def rank_stations(candidates: list[StationCandidate], profile: str = "balanced",
                   custom_overrides: dict | None = None) -> list[tuple[StationCandidate, float]]:
    """Convenience wrapper: returns (candidate, score) pairs sorted best-first."""
    weights = resolve_cos_weights(profile, custom_overrides)
    scores = compute_cos_scores(candidates, weights)
    return sorted(((c, scores[c.station_id]) for c in candidates), key=lambda pair: pair[1], reverse=True)
