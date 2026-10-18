import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from optimization.explainability import DecisionContext, build_explanation, render_explanation_paragraph


def _ctx(**overrides):
    defaults = dict(
        recommended_action="wait", action_kw=0.0,
        current_price_idx=1, current_grid_idx=1, current_solar_idx=0,
        target_soc_pct=90.0, is_feasible=True,
    )
    defaults.update(overrides)
    return DecisionContext(**defaults)


def test_infeasible_case_produces_target_infeasible_reason_first():
    ctx = _ctx(is_feasible=False, max_achievable_soc_pct=68.0, recommended_action="charge_now")
    reasons = build_explanation(ctx)
    assert reasons[0].reason_code == "target_infeasible"
    assert "68" in reasons[0].reason_text


def test_infeasible_reason_uses_actual_supplied_value_not_invented():
    ctx = _ctx(is_feasible=False, max_achievable_soc_pct=42.5)
    reasons = build_explanation(ctx)
    infeasible = next(r for r in reasons if r.reason_code == "target_infeasible")
    assert infeasible.supporting_value == 42.5


def test_price_advantage_reason_appears_when_waiting_and_price_drops():
    ctx = _ctx(recommended_action="wait", current_price_value=13.5, predicted_best_price_value=7.0,
               predicted_best_time_label="12:15 AM")
    reasons = build_explanation(ctx)
    codes = [r.reason_code for r in reasons]
    assert "electricity_price_advantage" in codes


def test_price_advantage_reason_absent_when_no_real_price_drop():
    ctx = _ctx(recommended_action="wait", current_price_value=8.0, predicted_best_price_value=7.95)
    reasons = build_explanation(ctx)
    codes = [r.reason_code for r in reasons]
    assert "electricity_price_advantage" not in codes


def test_price_advantage_percentage_matches_actual_math():
    ctx = _ctx(recommended_action="wait", current_price_value=10.0, predicted_best_price_value=5.0)
    reasons = build_explanation(ctx)
    r = next(r for r in reasons if r.reason_code == "electricity_price_advantage")
    assert r.supporting_value == 50.0
    assert "50%" in r.reason_text


def test_grid_advantage_only_when_grid_elevated_and_waiting():
    low_grid = _ctx(current_grid_idx=0, recommended_action="wait")
    high_grid = _ctx(current_grid_idx=2, recommended_action="wait")
    assert "grid_load_advantage" not in [r.reason_code for r in build_explanation(low_grid)]
    assert "grid_load_advantage" in [r.reason_code for r in build_explanation(high_grid)]


def test_renewable_reason_only_above_threshold():
    low_solar = _ctx(renewable_availability_frac=0.1)
    high_solar = _ctx(renewable_availability_frac=0.7)
    assert "renewable_availability" not in [r.reason_code for r in build_explanation(low_solar)]
    assert "renewable_availability" in [r.reason_code for r in build_explanation(high_solar)]


def test_cost_savings_reason_reflects_actual_numbers():
    ctx = _ctx(estimated_cost=186.0, immediate_cost=247.0)
    reasons = build_explanation(ctx)
    r = next(r for r in reasons if r.reason_code == "cost_savings")
    assert "186" in r.reason_text and "247" in r.reason_text and "61" in r.reason_text


def test_no_cost_savings_reason_when_costs_equal():
    ctx = _ctx(estimated_cost=200.0, immediate_cost=200.0)
    reasons = build_explanation(ctx)
    assert "cost_savings" not in [r.reason_code for r in reasons]


def test_never_returns_empty_explanation():
    ctx = _ctx(is_feasible=True, recommended_action="charge_now")  # minimal context, no extras
    reasons = build_explanation(ctx)
    assert len(reasons) >= 1


def test_render_explanation_paragraph_joins_all_reason_texts():
    ctx = _ctx(estimated_cost=100.0, immediate_cost=150.0)
    reasons = build_explanation(ctx)
    paragraph = render_explanation_paragraph(reasons)
    for r in reasons:
        assert r.reason_text in paragraph
