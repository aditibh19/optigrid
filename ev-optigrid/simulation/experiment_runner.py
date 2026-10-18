"""
Experiment runner (Phase 7, spec §15/§31).

Runs every algorithm (greedy / fixed_schedule / price_threshold / priority
/ sdp) across `n_replications` independent seeds derived from one base
seed, and aggregates mean/std/95% CI per metric — this is what
`experiment_results` rows (backend/models/misc.py) get populated from, and
what the Research Dashboard displays. Nothing here is hardcoded (spec §42):
every number is the output of `fleet_simulator.run_fleet_simulation`.
"""
from dataclasses import dataclass, asdict

import numpy as np

from simulation.fleet_simulator import FleetSimulationConfig, run_fleet_simulation, SimulationResult

ALGORITHMS = ("greedy", "fixed_schedule", "price_threshold", "priority", "sdp")

METRIC_FIELDS = (
    "total_cost", "peak_load_kw", "mean_waiting_slots", "soc_violations",
    "deadline_violations", "total_degradation_cost", "renewable_utilization_pct",
    "charger_utilization_pct", "energy_purchased_kwh",
)


@dataclass
class AggregatedMetric:
    mean: float
    std: float
    ci95_low: float
    ci95_high: float


@dataclass
class AlgorithmComparisonResult:
    algorithm: str
    n_replications: int
    metrics: dict  # metric_name -> AggregatedMetric


def _aggregate(values: list[float]) -> AggregatedMetric:
    arr = np.array(values, dtype=float)
    mean = float(arr.mean())
    std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    # Normal-approximation 95% CI on the mean (n typically small — this is
    # a standard, clearly-labeled approximation, not a claim of exactness).
    margin = 1.96 * std / np.sqrt(len(arr)) if len(arr) > 1 else 0.0
    return AggregatedMetric(mean=round(mean, 4), std=round(std, 4),
                             ci95_low=round(mean - margin, 4), ci95_high=round(mean + margin, 4))


def run_comparison_experiment(
    base_config: FleetSimulationConfig,
    n_replications: int = 5,
    algorithms: tuple = ALGORITHMS,
) -> list[AlgorithmComparisonResult]:
    """
    For each algorithm, runs `n_replications` simulations with different
    (but reproducible) seeds derived from `base_config.seed`, and returns
    aggregated statistics per metric.
    """
    results = []
    for algorithm in algorithms:
        raw_runs: list[SimulationResult] = []
        for rep in range(n_replications):
            rep_config = FleetSimulationConfig(**{**asdict(base_config), "seed": base_config.seed + rep})
            raw_runs.append(run_fleet_simulation(rep_config, algorithm=algorithm))

        metrics = {}
        for field in METRIC_FIELDS:
            values = [getattr(r, field) for r in raw_runs]
            metrics[field] = _aggregate(values)

        results.append(AlgorithmComparisonResult(
            algorithm=algorithm, n_replications=n_replications, metrics=metrics,
        ))
    return results


def print_comparison_table(results: list[AlgorithmComparisonResult]) -> None:
    """Human-readable console table — the same numbers the Research Dashboard renders as charts."""
    header = f"{'Algorithm':16s} " + " ".join(f"{m:>22s}" for m in METRIC_FIELDS)
    print(header)
    print("-" * len(header))
    for r in results:
        row = f"{r.algorithm:16s} "
        for field in METRIC_FIELDS:
            agg = r.metrics[field]
            row += f"{agg.mean:>14.2f}\u00b1{agg.std:<6.2f} "
        print(row)
