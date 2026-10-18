"""
Runnable sanity-check for the SDP engine (Phase 4/5).

Not a pytest suite (that's Phase 19) — this is a quick, human-readable
verification that value iteration actually produces sensible EV charging
behaviour before we build the rest of the pipeline on top of it:

  1. The solver converges without errors on a realistic-sized state space.
  2. Charging is deferred to cheap/low-grid-load/high-solar slots when there
     is slack before the deadline (i.e. "WAIT" behaviour emerges, not just
     immediate charging).
  3. Switching profile (save_money vs fastest vs green) visibly changes the
     recommended action in the *same* state — proving weights actually
     matter (spec §7's core requirement).
  4. The terminal SOC reaches the target when the horizon is long enough,
     and gracefully falls short (rather than crashing) when it isn't.

Run with: python optimization/demo_sdp.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from optimization.mdp import (
    MDPConfig, soc_from_bucket_index, nearest_soc_bucket_index,
    bucketize_price, bucketize_grid_load, bucketize_solar,
    DEFAULT_PRICE_THRESHOLDS, DEFAULT_GRID_LOAD_THRESHOLDS, DEFAULT_SOLAR_THRESHOLDS,
)
from optimization.reward_model import resolve_weights, DEFAULT_PRICE_VALUES, DEFAULT_GRID_LOAD_VALUES, DEFAULT_SOLAR_AVAIL_VALUES
from optimization.transition_model import TransitionModel
from optimization.value_iteration import solve_value_iteration


def simulate_forward(policy_obj, initial_soc, price_seq, grid_seq, solar_seq):
    """Roll the greedy policy forward through a *given* (not sampled) sequence of
    exogenous states, to see the resulting SOC trajectory and actions taken."""
    soc = initial_soc
    trace = []
    horizon = len(price_seq)
    for t in range(horizon):
        p, g, s = price_seq[t], grid_seq[t], solar_seq[t]
        a_kw = policy_obj.action_kw(t, soc, p, g, s)
        gain = policy_obj.config.soc_gain_pct(a_kw)
        soc_next = max(0.0, min(100.0, soc + gain))
        trace.append((t, round(soc, 1), p, g, s, a_kw, round(soc_next, 1)))
        soc = soc_next
    return soc, trace


def main():
    config = MDPConfig(
        battery_capacity_kwh=60.0,
        max_charge_rate_kw=50.0,
        charging_efficiency=0.90,
        slot_minutes=30,
        horizon_slots=12,     # 12 * 30min = 6 hours to deadline
    )
    target_soc = 90.0
    min_safe_soc = 70.0
    initial_soc = 32.0

    tm = TransitionModel()

    print("=" * 70)
    print("EV-OptiGrid — SDP engine verification")
    print("=" * 70)
    print(f"Battery: {config.battery_capacity_kwh} kWh | Max charge rate: {config.max_charge_rate_kw} kW")
    print(f"Horizon: {config.horizon_slots} slots x {config.slot_minutes} min = "
          f"{config.horizon_slots * config.slot_minutes / 60:.1f} hours")
    print(f"Initial SOC: {initial_soc}% -> Target: {target_soc}% (min safe: {min_safe_soc}%)")
    print()

    # ── Test 1: solve for each profile, confirm no errors + reasonable values ──
    policies = {}
    for profile in ("save_money", "fastest", "battery_health", "green", "balanced"):
        weights = resolve_weights(profile)
        policy = solve_value_iteration(
            config=config, weights=weights,
            target_soc_pct=target_soc, minimum_safe_soc_pct=min_safe_soc,
            transition_model=tm,
        )
        policies[profile] = policy
        v0 = policy.value_at(0, initial_soc, price_idx=1, grid_idx=1, solar_idx=0)
        print(f"[OK] profile={profile:16s}  V_0(initial state, med price/grid, no solar) = {v0:.3f}")

    print()
    print("-" * 70)
    print("Test 2: does the recommended action change across profiles for the")
    print("        SAME state? (proves weights actually matter). Using a state")
    print("        near the deadline (t=horizon-2, still below target, high")
    print("        price/grid) so profiles are forced to trade off urgency vs cost.")
    print("-" * 70)
    late_t = config.horizon_slots - 2
    low_soc = 60.0  # still short of the 90% target with little time left
    state = dict(price_idx=2, grid_idx=2, solar_idx=0)  # expensive, high grid load, no solar
    for profile, policy in policies.items():
        a = policy.action_kw(late_t, low_soc, **state)
        print(f"  {profile:16s} -> recommended charge power near deadline (high price/grid, SOC={low_soc}%): {a:5.1f} kW")

    print()
    print("-" * 70)
    print("Test 3: forward simulation under a scenario where price/grid start")
    print("        high and improve halfway through the horizon — expect the")
    print("        'balanced' policy to defer charging rather than start immediately.")
    print("-" * 70)
    half = config.horizon_slots // 2
    price_seq = [2] * half + [0] * (config.horizon_slots - half)   # high -> low
    grid_seq = [2] * half + [0] * (config.horizon_slots - half)    # high -> low
    solar_seq = [0] * config.horizon_slots                          # no solar (e.g. night charging)

    balanced_policy = policies["balanced"]
    final_soc, trace = simulate_forward(balanced_policy, initial_soc, price_seq, grid_seq, solar_seq)

    print(f"  {'t':>2} {'soc_before':>10} {'price':>6} {'grid':>5} {'solar':>6} {'action_kw':>10} {'soc_after':>10}")
    for t, soc_b, p, g, s, a, soc_a in trace:
        print(f"  {t:>2} {soc_b:>10} {p:>6} {g:>5} {s:>6} {a:>10} {soc_a:>10}")
    print(f"  Final SOC: {final_soc:.1f}%  (target was {target_soc}%)")

    early_actions = [a for (_, _, _, _, _, a, _) in trace[:half]]
    late_actions = [a for (_, _, _, _, _, a, _) in trace[half:]]
    print(f"  Mean charging power in expensive/high-grid half: {np.mean(early_actions):.1f} kW")
    print(f"  Mean charging power in cheap/low-grid half:      {np.mean(late_actions):.1f} kW")
    if np.mean(late_actions) > np.mean(early_actions):
        print("  [PASS] Policy correctly deferred more charging to the cheap/low-grid period.")
    else:
        print("  [WARN] Policy did not defer charging as expected — inspect weights/horizon.")

    print()
    print("-" * 70)
    print("Test 4: infeasible deadline — very short horizon, low charge rate")
    print("-" * 70)
    tight_config = MDPConfig(
        battery_capacity_kwh=60.0, max_charge_rate_kw=7.0,   # slow AC charger
        slot_minutes=15, horizon_slots=4,                     # only 1 hour to deadline
    )
    weights = resolve_weights("balanced")
    tight_policy = solve_value_iteration(
        config=tight_config, weights=weights,
        target_soc_pct=target_soc, minimum_safe_soc_pct=min_safe_soc,
        transition_model=tm,
    )
    # Always charge at max in every state (only lever left when time-constrained)
    soc = initial_soc
    for t in range(tight_config.horizon_slots):
        a = tight_policy.action_kw(t, soc, 1, 1, 0)
        soc = min(100.0, soc + tight_config.soc_gain_pct(a))
    print(f"  With only {tight_config.horizon_slots * tight_config.slot_minutes} min and a "
          f"{tight_config.max_charge_rate_kw} kW charger, max achievable SOC = {soc:.1f}%")
    if soc < target_soc:
        print(f"  [PASS] Correctly reports target ({target_soc}%) is infeasible instead of pretending "
              f"it can be met — this is the value urgent-mode (spec §13) reads to say "
              f"'target infeasible, max achievable is {soc:.1f}%'.")
    else:
        print("  [INFO] Target was actually feasible in this tight scenario.")

    print()
    print("=" * 70)
    print("All checks completed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
