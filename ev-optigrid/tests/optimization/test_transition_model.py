import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pytest

from optimization.transition_model import (
    build_default_transition_matrix, estimate_transition_matrix, TransitionModel,
)


def test_default_transition_matrix_rows_sum_to_one():
    m = build_default_transition_matrix(3, persistence=0.7)
    assert np.allclose(m.sum(axis=1), 1.0)


def test_default_transition_matrix_diagonal_dominant():
    m = build_default_transition_matrix(3, persistence=0.7)
    for i in range(3):
        assert m[i, i] == max(m[i])


def test_estimated_transition_matrix_rows_sum_to_one():
    seq = [0, 0, 1, 1, 2, 1, 0, 0, 1, 2, 2, 1, 0]
    m = estimate_transition_matrix(seq, n_levels=3)
    assert np.allclose(m.sum(axis=1), 1.0)


def test_estimated_transition_matrix_reflects_observed_pattern():
    # Sequence that always stays at 0 once it gets there
    seq = [0] * 50
    m = estimate_transition_matrix(seq, n_levels=3, smoothing=0.01)
    assert m[0, 0] > 0.9  # near-certain self-transition


def test_transition_model_validates_matrix_shape():
    bad_matrix = np.array([[0.5, 0.5], [0.5, 0.5]])  # wrong shape for N_PRICE=3
    with pytest.raises(AssertionError):
        TransitionModel(price_matrix=bad_matrix)


def test_transition_model_next_state_distribution_sums_to_one():
    tm = TransitionModel()
    dist = tm.next_state_distribution(price_idx=1, grid_idx=1, solar_idx=1)
    total_prob = sum(p for p, *_ in dist)
    assert total_prob == pytest.approx(1.0, abs=1e-6)


def test_transition_model_distribution_entries_are_valid_indices():
    tm = TransitionModel()
    dist = tm.next_state_distribution(0, 0, 0)
    for prob, p, g, s in dist:
        assert 0 <= p < 3 and 0 <= g < 3 and 0 <= s < 3
        assert 0.0 < prob <= 1.0
