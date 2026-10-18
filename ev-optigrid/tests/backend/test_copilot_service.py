import sys
from pathlib import Path
from datetime import time as dt_time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from services.copilot_service import (
    classify_intent, RuleBasedExtractor, validate_parameters, handle_message, ExtractedParameters,
)


# ── Intent classification ───────────────────────────────────────────────

def test_classify_plan_charging():
    assert classify_intent("I need 85% by 6:30 tomorrow morning.") == "plan_charging"


def test_classify_find_charger():
    assert classify_intent("Find a charger near me.") == "find_charger"


def test_classify_explain_decision():
    assert classify_intent("Why are you telling me to wait?") == "explain_decision"


def test_classify_what_if():
    assert classify_intent("What if I leave one hour earlier?") == "what_if"


def test_classify_cost_query():
    assert classify_intent("How much money will I save?") == "cost_query"


def test_classify_price_sensitivity():
    assert classify_intent("What happens if electricity gets expensive?") == "price_sensitivity"


def test_classify_compare_chargers():
    assert classify_intent("Which charger is fastest?") == "compare_chargers"


def test_classify_unknown_for_unrelated_text():
    assert classify_intent("Tell me a joke.") == "unknown"


# ── Extraction ──────────────────────────────────────────────────────────

def test_extract_percentage():
    e = RuleBasedExtractor().extract("I need 85% by 6:30 tomorrow morning.")
    assert e.target_soc_pct == 85.0


def test_extract_time_with_ampm():
    e = RuleBasedExtractor().extract("I need to reach the airport by 6 AM.")
    assert e.deadline_time == dt_time(hour=6, minute=0)


def test_extract_destination():
    e = RuleBasedExtractor().extract("I need to reach the airport by 6 AM.")
    assert e.destination_text == "airport"


def test_extract_bare_time_with_morning_daypart():
    e = RuleBasedExtractor().extract("Charge to 90% by 6:30 tomorrow morning.")
    assert e.deadline_time == dt_time(hour=6, minute=30)


def test_extract_bare_time_with_night_daypart_becomes_pm():
    e = RuleBasedExtractor().extract("Charge to 90% by 6:30 tonight.")
    assert e.deadline_time == dt_time(hour=18, minute=30)


def test_extract_minutes_from_now():
    e = RuleBasedExtractor().extract("I need to leave in 20 minutes.")
    assert e.deadline_minutes_from_now == 20


def test_extract_no_percentage_returns_none():
    e = RuleBasedExtractor().extract("Find a charger near me.")
    assert e.target_soc_pct is None


# ── Validation ──────────────────────────────────────────────────────────

def test_validate_valid_plan_charging_with_target():
    params = ExtractedParameters(intent="plan_charging", target_soc_pct=85.0)
    result = validate_parameters(params)
    assert result.is_valid


def test_validate_rejects_out_of_range_target():
    params = ExtractedParameters(intent="plan_charging", target_soc_pct=150.0)
    result = validate_parameters(params)
    assert not result.is_valid
    assert any("out of the valid" in e for e in result.errors)


def test_validate_rejects_plan_charging_with_nothing_specified():
    params = ExtractedParameters(intent="plan_charging")
    result = validate_parameters(params)
    assert not result.is_valid


def test_validate_find_charger_needs_no_target():
    params = ExtractedParameters(intent="find_charger")
    result = validate_parameters(params)
    assert result.is_valid


# ── Full orchestration ──────────────────────────────────────────────────

def test_handle_message_calls_optimizer_only_when_valid():
    calls = []

    def fake_optimizer(extracted):
        calls.append(extracted)
        return {"recommended_action": "wait", "explanation_paragraph": "Because prices drop later."}

    response = handle_message("I need 85% by 6:30 tomorrow morning.", optimizer_callback=fake_optimizer)
    assert len(calls) == 1
    assert response.optimizer_result["recommended_action"] == "wait"
    assert response.explanation_text == "Because prices drop later."


def test_handle_message_does_not_call_optimizer_when_invalid():
    calls = []

    def fake_optimizer(extracted):
        calls.append(extracted)
        return {}

    response = handle_message("When should I charge?", optimizer_callback=fake_optimizer)
    assert len(calls) == 0
    assert response.optimizer_result is None
    assert not response.validation.is_valid


def test_handle_message_does_not_call_optimizer_for_non_planning_intent():
    calls = []

    def fake_optimizer(extracted):
        calls.append(extracted)
        return {}

    handle_message("Find a charger near me.", optimizer_callback=fake_optimizer)
    assert len(calls) == 0   # find_charger doesn't go through the SDP optimizer


def test_llm_never_asked_to_invent_schedule():
    """
    Architectural check: handle_message's optimizer_result comes ONLY from
    the injected optimizer_callback, never fabricated by handle_message
    itself — i.e. there is no code path that returns a recommended_action
    without going through the callback.
    """
    response = handle_message("I need 85% by 6:30 tomorrow morning.", optimizer_callback=None)
    assert response.optimizer_result is None
