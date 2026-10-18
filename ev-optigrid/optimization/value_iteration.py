"""
Value iteration / backward induction (Phase 4/5, spec §6).

Solves the finite-horizon Bellman equation:

    V_t(s) = min_a [ C(s,a) + gamma * sum_s' P(s'|s,a) V_{t+1}(s') ]
    pi_t(s) = argmin_a [ ... ]

backward from the deadline slot `t = horizon` (terminal cost only) to
`t = 0` (now). See docs/MDP.md for why finite-horizon backward induction is
the correct formulation here (a known deadline), vs. the more commonly
quoted infinite-horizon discounted form.

State axes, fixed order throughout this module: (soc, price, grid, solar).
Only SOC's transition depends on the action (deterministic battery
physics); price/grid/solar transition independently of the action via the
Markov matrices in `transition_model.py`.
"""
from dataclasses import dataclass

import numpy as np

from optimization.mdp import (
    MDPConfig, N_SOC, N_PRICE, N_GRID, N_SOLAR,
    nearest_soc_bucket_index, soc_from_bucket_index, soc_transition_distribution,
)
from optimization.transition_model import TransitionModel
from optimization.reward_model import (
    ProfileWeights, step_cost, terminal_cost,
    DEFAULT_PRICE_VALUES, DEFAULT_GRID_LOAD_VALUES, DEFAULT_SOLAR_AVAIL_VALUES,
)


@dataclass
class SolvedPolicy:
    """Result of value iteration: value function + greedy policy over the whole horizon."""
    V: np.ndarray          # shape (horizon+1, N_SOC, N_PRICE, N_GRID, N_SOLAR)
    policy: np.ndarray     # shape (horizon,   N_SOC, N_PRICE, N_GRID, N_SOLAR) -> action index
    actions_kw: tuple
    config: MDPConfig
    target_soc_pct: float
    minimum_safe_soc_pct: float

    def action_kw(self, t: int, soc_pct: float, price_idx: int, grid_idx: int, solar_idx: int) -> float:
        """Policy lookup for a (possibly off-grid) SOC value at time slot t."""
        t = max(0, min(self.policy.shape[0] - 1, t))
        soc_idx = nearest_soc_bucket_index(soc_pct)
        a_idx = int(self.policy[t, soc_idx, price_idx, grid_idx, solar_idx])
        return self.actions_kw[a_idx]

    def value_at(self, t: int, soc_pct: float, price_idx: int, grid_idx: int, solar_idx: int) -> float:
        soc_idx = nearest_soc_bucket_index(soc_pct)
        return float(self.V[t, soc_idx, price_idx, grid_idx, solar_idx])


def _joint_transition_tensor(tm: TransitionModel) -> np.ndarray:
    """T[p,g,s,i,j,k] = P(price'=i|p) * P(grid'=j|g) * P(solar'=k|s) — shape (3,3,3,3,3,3)."""
    T = np.einsum("pi,gj,sk->pgsijk", tm.price_matrix, tm.grid_matrix, tm.solar_matrix)
    return T


def solve_value_iteration(
    config: MDPConfig,
    weights: ProfileWeights,
    target_soc_pct: float,
    minimum_safe_soc_pct: float,
    transition_model: TransitionModel | None = None,
    gamma: float = 0.99,
    price_values: dict = DEFAULT_PRICE_VALUES,
    grid_values: dict = DEFAULT_GRID_LOAD_VALUES,
    solar_values: dict = DEFAULT_SOLAR_AVAIL_VALUES,
) -> SolvedPolicy:
    tm = transition_model or TransitionModel()
    T = _joint_transition_tensor(tm)  # (3,3,3,3,3,3)

    actions = config.feasible_actions_kw()
    n_actions = len(actions)
    horizon = config.horizon_slots

    V = np.zeros((horizon + 1, N_SOC, N_PRICE, N_GRID, N_SOLAR))
    policy = np.zeros((horizon, N_SOC, N_PRICE, N_GRID, N_SOLAR), dtype=int)

    # Terminal cost at t = horizon: depends only on SOC, broadcast across price/grid/solar.
    for soc_idx in range(N_SOC):
        soc_pct = soc_from_bucket_index(soc_idx)
        tc = terminal_cost(soc_pct, target_soc_pct, minimum_safe_soc_pct, weights)
        V[horizon, soc_idx, :, :, :] = tc

    # Precompute per-action, per-soc: the continuous gain, resulting
    # continuous soc_after (clamped), and the interpolated distribution
    # over bracketing soc buckets used for the *value continuation* only —
    # cost is computed from the true continuous soc_after, not a
    # bucket-rounded one.
    def _transition_info(a_kw, soc_idx):
        soc_pct = soc_from_bucket_index(soc_idx)
        gain_pct = config.soc_gain_pct(a_kw)
        soc_after_continuous = max(0.0, min(100.0, soc_pct + gain_pct))
        dist = soc_transition_distribution(soc_pct, gain_pct)
        return soc_after_continuous, dist

    for t in range(horizon - 1, -1, -1):
        V_next = V[t + 1]  # (N_SOC, N_PRICE, N_GRID, N_SOLAR)

        for soc_idx in range(N_SOC):
            soc_pct = soc_from_bucket_index(soc_idx)
            best_total = None
            best_action_idx = 0

            # Actions are evaluated in their natural (ascending power) order.
            # Ties default to the FIRST-seen action — i.e. 0 kW — which is
            # the sensible default ("don't draw power unless it clearly
            # helps"). This matters at e.g. 100% SOC, where every action
            # delivers zero effective power and all costs are identically
            # zero: defaulting to 0 kW avoids reporting a nonsensical
            # "charge at 50 kW" recommendation for a battery that can't
            # accept any more charge. (An earlier version of this loop
            # iterated largest-to-smallest to work around a since-fixed
            # discretization issue — see docs/MDP.md §12 — but that
            # exposed a real bug: `best_action_idx` was hardcoded to
            # np.zeros(...) on the first action regardless of which action
            # index was actually processed first, silently corrupting the
            # policy whenever the optimal action wasn't literally index 0.
            # Both issues are now fixed at their actual source — the
            # interpolated transition below — so plain ascending order is
            # correct and simplest.)
            for a_idx, a_kw in enumerate(actions):
                soc_after_pct, soc_dist = _transition_info(a_kw, soc_idx)

                # Effective delivered power: a real charger stops delivering
                # once the battery is full, so if `soc_after_pct` is clamped
                # at 100 the vehicle didn't actually draw `a_kw` for the
                # whole slot. Using the nominal action here would let the
                # optimizer "earn" cost/renewable terms for power that was
                # never actually delivered (caught by
                # tests/optimization/test_value_iteration.py::
                # test_full_soc_never_charges_further, which failed before
                # this fix — see docs/MDP.md §8 for the electricity-cost
                # normalization bug this is the sibling of).
                actual_gain_pct = soc_after_pct - soc_pct
                if config.slot_hours > 0 and config.charging_efficiency > 0:
                    effective_kw = (
                        (actual_gain_pct / 100.0) * config.battery_capacity_kwh
                    ) / (config.charging_efficiency * config.slot_hours)
                else:
                    effective_kw = 0.0
                effective_kw = max(0.0, min(a_kw, effective_kw))

                # Cost C(s,a) for every (price, grid, solar) combo at once.
                cost_grid = np.zeros((N_PRICE, N_GRID, N_SOLAR))
                for p in range(N_PRICE):
                    for g in range(N_GRID):
                        for s in range(N_SOLAR):
                            cost_grid[p, g, s] = step_cost(
                                soc_before_pct=soc_pct,
                                soc_after_pct=soc_after_pct,
                                action_kw=effective_kw,
                                max_charge_rate_kw=config.max_charge_rate_kw,
                                price_idx=p, grid_idx=g, solar_idx=s,
                                slot_hours=config.slot_hours,
                                weights=weights,
                                price_values=price_values,
                                grid_values=grid_values,
                                solar_values=solar_values,
                            )

                # Expected future value for every (price, grid, solar) combo,
                # marginalizing over BOTH the interpolated soc-bucket
                # distribution and the price/grid/solar joint transition:
                # E[p,g,s] = sum_soc' P(soc') * sum_ijk T[p,g,s,i,j,k] * V_next[soc',i,j,k]
                expected_future = np.zeros((N_PRICE, N_GRID, N_SOLAR))
                for soc_prob, soc_after_idx in soc_dist:
                    v_next_slice = V_next[soc_after_idx]  # (N_PRICE, N_GRID, N_SOLAR)
                    expected_future += soc_prob * np.einsum("pgsijk,ijk->pgs", T, v_next_slice)

                total = cost_grid + gamma * expected_future  # (N_PRICE, N_GRID, N_SOLAR)

                if best_total is None:
                    best_total = total.copy()
                    best_action_idx = np.full((N_PRICE, N_GRID, N_SOLAR), a_idx, dtype=int)
                else:
                    improved = total < best_total
                    best_total = np.where(improved, total, best_total)
                    best_action_idx = np.where(improved, a_idx, best_action_idx)

            V[t, soc_idx] = best_total
            policy[t, soc_idx] = best_action_idx

    return SolvedPolicy(
        V=V, policy=policy, actions_kw=actions, config=config,
        target_soc_pct=target_soc_pct, minimum_safe_soc_pct=minimum_safe_soc_pct,
    )
