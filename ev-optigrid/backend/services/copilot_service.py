"""
AI Copilot service (Phase 15, spec §14).

Architecture (spec §14):

    USER -> LLM parameter extraction -> Schema validation -> Optimization API
         -> SDP engine -> Verified result -> LLM explanation

The LLM MUST NOT invent the charging schedule — the mathematical optimizer
makes that decision. This module implements the extraction + validation +
orchestration steps; the "LLM" for extraction is a rule-based parser by
default (`RuleBasedExtractor`), so the copilot demo works with zero API
keys configured. A real `LLMProvider` (`services/providers/base.py`) can
replace ONLY the extraction step later — it still may not skip schema
validation or call the optimizer's job itself.
"""
import re
from dataclasses import dataclass, field
from datetime import time as dt_time


@dataclass
class ExtractedParameters:
    intent: str                                  # see INTENTS below
    target_soc_pct: float | None = None
    deadline_time: dt_time | None = None
    deadline_minutes_from_now: int | None = None  # for "leave in 20 minutes" style phrasing
    destination_text: str | None = None
    raw_message: str = ""


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list = field(default_factory=list)


INTENTS = (
    "plan_charging",       # "when should I charge", "I need 85% by 6:30"
    "find_charger",        # "find a charger near me"
    "explain_decision",    # "why is this charger better", "why are you telling me to wait"
    "what_if",             # "what if I leave one hour earlier"
    "cost_query",          # "how much money will I save"
    "price_sensitivity",   # "what happens if electricity gets expensive"
    "compare_chargers",    # "which charger is fastest"
    "unknown",
)

_INTENT_KEYWORDS = [
    ("what_if", ["what if", "what happens if i", "suppose i"]),
    ("price_sensitivity", ["electricity gets expensive", "price goes up", "price increases"]),
    ("explain_decision", ["why is", "why are you", "why should i", "why not", "why did you"]),
    ("cost_query", ["how much money", "how much will i save", "how much does it cost", "savings"]),
    ("compare_chargers", ["which charger", "fastest charger", "compare"]),
    ("find_charger", ["find a charger", "charger near me", "nearby charger", "find charging"]),
    ("plan_charging", ["when should i charge", "need to reach", "need to leave", "i need", "charge by", "target"]),
]


def classify_intent(message: str) -> str:
    lowered = message.lower()
    for intent, phrases in _INTENT_KEYWORDS:
        if any(p in lowered for p in phrases):
            return intent
    return "unknown"


class RuleBasedExtractor:
    """
    Regex/keyword parameter extraction — the DEMO stand-in for an LLM
    extraction step (spec §39: LLM is a swappable provider). Handles the
    example phrasings from spec §14 directly:
        "I need 85% by 6:30 tomorrow morning."
        "I need to reach the airport by 6 AM."
        "I need to leave in 20 minutes."
    """

    _PCT_RE = re.compile(r"(\d{1,3})\s*%")
    _TIME_WITH_AMPM_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)
    # Bare "H:MM" with no am/pm attached, disambiguated by a nearby
    # daypart word ("morning"/"night"/"evening"/"tonight") — covers phrasing
    # like "85% by 6:30 tomorrow morning" (spec §14's own example), which
    # the am/pm-only regex above does not match.
    _TIME_BARE_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
    _DAYPART_RE = re.compile(r"\b(morning|afternoon|evening|night|tonight)\b", re.IGNORECASE)
    _MINUTES_FROM_NOW_RE = re.compile(r"leave in (\d{1,3})\s*min", re.IGNORECASE)
    _DESTINATION_RE = re.compile(r"reach (?:the )?([a-zA-Z ]+?)(?:\s+by\b|\s*$)", re.IGNORECASE)

    def extract(self, message: str) -> ExtractedParameters:
        intent = classify_intent(message)

        target_soc = None
        pct_match = self._PCT_RE.search(message)
        if pct_match:
            target_soc = float(pct_match.group(1))

        deadline_time = self._extract_time(message)

        minutes_from_now = None
        min_match = self._MINUTES_FROM_NOW_RE.search(message)
        if min_match:
            minutes_from_now = int(min_match.group(1))

        destination = None
        dest_match = self._DESTINATION_RE.search(message)
        if dest_match:
            destination = dest_match.group(1).strip()

        return ExtractedParameters(
            intent=intent, target_soc_pct=target_soc, deadline_time=deadline_time,
            deadline_minutes_from_now=minutes_from_now, destination_text=destination,
            raw_message=message,
        )

    def _extract_time(self, message: str) -> dt_time | None:
        # First choice: an explicit am/pm time ("6 AM").
        m = self._TIME_WITH_AMPM_RE.search(message)
        if m:
            hour = int(m.group(1)) % 12
            minute = int(m.group(2) or 0)
            if m.group(3).lower() == "pm":
                hour += 12
            return dt_time(hour=hour, minute=minute)

        # Fallback: a bare "H:MM" plus a daypart word to disambiguate
        # am/pm ("6:30 tomorrow morning" -> 6:30 AM; "6:30 tonight" -> PM).
        bare = self._TIME_BARE_RE.search(message)
        daypart = self._DAYPART_RE.search(message)
        if bare and daypart:
            hour = int(bare.group(1)) % 12
            minute = int(bare.group(2))
            word = daypart.group(1).lower()
            if word in ("afternoon", "evening", "night", "tonight"):
                hour += 12
            return dt_time(hour=hour, minute=minute)
        return None


def validate_parameters(params: ExtractedParameters) -> ValidationResult:
    """
    Schema validation step (spec §14) — the extraction step above is never
    trusted blindly. Bad or missing values are reported as errors rather
    than silently passed through to the optimizer.
    """
    errors = []
    if params.target_soc_pct is not None and not (0 <= params.target_soc_pct <= 100):
        errors.append(f"target_soc_pct {params.target_soc_pct} is out of the valid 0-100 range.")
    if params.intent not in INTENTS:
        errors.append(f"Unrecognized intent: {params.intent}")
    if params.intent == "plan_charging" and params.target_soc_pct is None and params.deadline_time is None \
            and params.deadline_minutes_from_now is None:
        errors.append("plan_charging intent needs at least a target SOC or a deadline.")
    return ValidationResult(is_valid=(len(errors) == 0), errors=errors)


@dataclass
class CopilotResponse:
    intent: str
    extracted: ExtractedParameters
    validation: ValidationResult
    optimizer_result: dict = None    # populated by the caller-supplied optimizer callback
    explanation_text: str = None


def handle_message(message: str, optimizer_callback=None, extractor: RuleBasedExtractor = None) -> CopilotResponse:
    """
    Orchestrates the full flow: extract -> validate -> (if valid) call the
    optimizer -> attach explanation. `optimizer_callback`, if given, is
    called as `optimizer_callback(extracted_parameters) -> dict` and stands
    in for the real `POST /api/charging/optimize` call (Phase 12) — kept as
    a dependency-injected callback here so this module has no FastAPI/DB
    dependency and is directly unit-testable.
    """
    extractor = extractor or RuleBasedExtractor()
    extracted = extractor.extract(message)
    validation = validate_parameters(extracted)

    optimizer_result = None
    explanation_text = None
    if validation.is_valid and optimizer_callback is not None and extracted.intent in ("plan_charging", "what_if"):
        optimizer_result = optimizer_callback(extracted)
        if optimizer_result and "explanation_paragraph" in optimizer_result:
            explanation_text = optimizer_result["explanation_paragraph"]

    return CopilotResponse(
        intent=extracted.intent, extracted=extracted, validation=validation,
        optimizer_result=optimizer_result, explanation_text=explanation_text,
    )
