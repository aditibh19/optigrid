"""
What-If Simulator + Research Dashboard endpoints (Phase 12, spec §15/§26/§31).
"""
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from database.session import get_db
from models.misc import Experiment, ExperimentResult

router = APIRouter()

# The SDP policy is solved per vehicle per time slot, and the policy cache is keyed on
# each vehicle's own battery/charge-rate/target plus the REMAINING horizon, so in a
# heterogeneous fleet almost every lookup is a miss. Cost is therefore ~
# cars x repetitions x time slots solves at ~16 solves/s (measured). A default-sized
# run (25 cars x 5 reps x 48 slots = 6,000 solves) took >5 min and wrote ~200 MB of
# cache, so runs above this budget are refused up front instead of hanging.
MAX_SIM_WORK = int(os.getenv("SIM_MAX_WORK", "1500"))
SOLVES_PER_SECOND_COLD = 16


def estimated_work(num_evs: int, n_replications: int, horizon_slots: int) -> int:
    return num_evs * n_replications * horizon_slots


class SimulationRequest(BaseModel):
    num_evs: int = Field(10, gt=0, le=500)
    num_chargers: int = Field(4, gt=0, le=100)
    charger_power_kw: float = Field(50.0, gt=0)
    grid_capacity_kw: float = Field(150.0, gt=0)
    horizon_slots: int = Field(24, gt=0, le=200)
    slot_minutes: int = Field(15, gt=0)
    seed: int = 42
    n_replications: int = Field(2, gt=0, le=20)
    algorithms: list[str] | None = None


@router.get("/limits")
def simulation_limits():
    """Lets clients show the cost estimate before a run is started."""
    return {"max_work": MAX_SIM_WORK, "solves_per_second_cold": SOLVES_PER_SECOND_COLD,
            "work_formula": "num_evs * n_replications * horizon_slots"}


@router.post("/run")
def run_simulation(payload: SimulationRequest, db: Session = Depends(get_db)):
    from simulation.fleet_simulator import FleetSimulationConfig
    from simulation.experiment_runner import run_comparison_experiment, ALGORITHMS

    uses_sdp = payload.algorithms is None or "sdp" in payload.algorithms
    work = estimated_work(payload.num_evs, payload.n_replications, payload.horizon_slots)
    if uses_sdp and work > MAX_SIM_WORK:
        raise HTTPException(status_code=422, detail=(
            f"This run would solve up to {work:,} optimiser policies (cars x repetitions x time slots), "
            f"roughly {work / SOLVES_PER_SECOND_COLD / 60:.0f} min on a first run. The limit is {MAX_SIM_WORK:,}. "
            f"Reduce the number of cars, repetitions or time slots."))

    config = FleetSimulationConfig(
        num_evs=payload.num_evs, num_chargers=payload.num_chargers, charger_power_kw=payload.charger_power_kw,
        grid_capacity_kw=payload.grid_capacity_kw, horizon_slots=payload.horizon_slots,
        slot_minutes=payload.slot_minutes, seed=payload.seed,
    )
    algorithms = tuple(payload.algorithms) if payload.algorithms else ALGORITHMS
    results = run_comparison_experiment(config, n_replications=payload.n_replications, algorithms=algorithms)

    experiment = Experiment(name=f"sim-{payload.num_evs}ev-{payload.num_chargers}ch", config_json=payload.model_dump())
    db.add(experiment)
    db.flush()
    for r in results:
        db.add(ExperimentResult(
            experiment_id=experiment.id, algorithm=r.algorithm,
            mean_cost=r.metrics["total_cost"].mean, std_cost=r.metrics["total_cost"].std,
            mean_wait_min=r.metrics["mean_waiting_slots"].mean, peak_load_kw=r.metrics["peak_load_kw"].mean,
            soc_violations=int(r.metrics["soc_violations"].mean), deadline_violations=int(r.metrics["deadline_violations"].mean),
            battery_degradation_score=r.metrics["total_degradation_cost"].mean,
            renewable_utilization_pct=r.metrics["renewable_utilization_pct"].mean,
            charger_utilization_pct=r.metrics["charger_utilization_pct"].mean,
            energy_purchased_kwh=r.metrics["energy_purchased_kwh"].mean,
        ))
    db.commit()

    return {
        "experiment_id": experiment.id,
        "results": [{"algorithm": r.algorithm, "n_replications": r.n_replications,
                     "metrics": {k: v.__dict__ for k, v in r.metrics.items()}} for r in results],
    }


@router.get("/results")
def get_simulation_results(experiment_id: str, db: Session = Depends(get_db)):
    rows = db.query(ExperimentResult).filter_by(experiment_id=experiment_id).all()
    return [{"algorithm": r.algorithm, "mean_cost": r.mean_cost, "std_cost": r.std_cost,
              "mean_wait_min": r.mean_wait_min, "peak_load_kw": r.peak_load_kw,
              "soc_violations": r.soc_violations, "deadline_violations": r.deadline_violations,
              "renewable_utilization_pct": r.renewable_utilization_pct} for r in rows]
