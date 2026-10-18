"""
Station service (Phase 12). Discovers nearby/route stations via the
configured ChargingStationProvider, predicts queue/wait via
ml/queue_predictor.py, scores them with the Charging Opportunity Score, and
returns them ranked — every station tagged with its real `source`.
"""
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from optimization.station_optimizer import StationCandidate, rank_stations
from optimization.battery_model import compute_degradation_cost


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    import math
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def get_ranked_nearby_stations(
    location_lat: float, location_lng: float, radius_km: float, limit: int,
    profile: str, vehicle_max_charge_rate_kw: float, target_soc_pct: float, current_soc_pct: float,
):
    """
    Returns a list of dicts ready to serialize as StationCardSchema. Uses
    the demo provider stack by default (Phase 10); swapping in real
    providers requires no change here since it goes through
    services.providers.factory.
    """
    from services.providers.factory import get_station_provider
    from services.providers.base import Coordinates
    from ml import queue_predictor
    from ml.queue_predictor import predict_queue_and_wait
    # Train-on-first-use, same pattern as api/predictions.py. (The old code
    # wrapped the *import* in try/except FileNotFoundError, which can never
    # fire — the error is raised later, on model load.)
    queue_model_available = True
    try:
        from ml.model_utils import ensure_trained
        ensure_trained(queue_predictor)
    except Exception:
        queue_model_available = False

    provider = get_station_provider()
    location = Coordinates(lat=location_lat, lng=location_lng)
    stations = provider.find_nearby(location, radius_km=radius_km, limit=limit)

    now = datetime.utcnow()
    candidates = []
    raw_by_id = {}
    for s in stations:
        distance_km = _haversine_km(location_lat, location_lng, s.lat, s.lng)
        available = [c for c in s.connectors if c["status"] == "available"]
        best_connector = max(s.connectors, key=lambda c: c["power_kw"], default=None)
        power_kw = best_connector["power_kw"] if best_connector else 7.4
        price = best_connector["price_per_kwh"] if best_connector else 8.0

        if queue_model_available:
            q = predict_queue_and_wait(hour=now.hour, weekday=now.weekday(),
                                        station_capacity=max(1, len(s.connectors)), station_popularity=1.0)
            predicted_queue, predicted_wait = q["predicted_queue"], q["predicted_wait_min"]
        else:
            predicted_queue, predicted_wait = 0.0, 0.0

        soc_gap = max(0.0, target_soc_pct - current_soc_pct)
        charge_power = min(power_kw, vehicle_max_charge_rate_kw)
        charging_duration_min = (soc_gap / 100.0) * 60.0 * 60.0 / max(charge_power, 1e-6) if charge_power > 0 else 999.0
        travel_time_min = (distance_km / 40.0) * 60.0   # assumed avg speed, matches DemoRoutingProvider
        battery_impact = compute_degradation_cost(
            soc_before=current_soc_pct, soc_after=min(100.0, current_soc_pct + soc_gap),
            charge_power_kw=charge_power, max_charge_rate_kw=vehicle_max_charge_rate_kw,
        )
        session_cost = charge_power * (charging_duration_min / 60.0) * price

        candidate = StationCandidate(
            station_id=s.station_id, name=s.name, charging_cost=session_cost,
            travel_time_min=travel_time_min, distance_km=distance_km,
            predicted_wait_min=predicted_wait, charging_duration_min=charging_duration_min,
            battery_impact=battery_impact, grid_load_pct=60.0,   # live grid % plugged in at call time in production
            renewable_availability=0.2, connector_availability_frac=len(available) / max(1, len(s.connectors)),
        )
        candidates.append(candidate)
        raw_by_id[s.station_id] = (s, distance_km, predicted_queue, predicted_wait)

    ranked = rank_stations(candidates, profile=profile)

    result = []
    for candidate, score in ranked:
        s, distance_km, predicted_queue, predicted_wait = raw_by_id[candidate.station_id]
        result.append({
            "station_id": s.station_id, "name": s.name, "lat": s.lat, "lng": s.lng,
            "distance_km": round(distance_km, 2), "connectors": s.connectors,
            "predicted_queue": predicted_queue, "predicted_wait_min": predicted_wait,
            "cos_score": score, "source": s.source,
        })
    return result
