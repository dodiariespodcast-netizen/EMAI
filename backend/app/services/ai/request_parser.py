"""Turns a physician's free-text ask ("I need Dec 22-29 off for vacation,
this one's important") into a structured time-off request.

Uses Claude tool-calling for high-quality extraction when an API key is
configured; falls back to a small deterministic parser otherwise so the
feature never hard-fails a request submission.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.models.enums import RequestPriority, TimeOffType
from app.services.ai.client import get_client

_EXTRACT_TOOL = {
    "name": "extract_time_off_request",
    "description": "Extract a structured time-off request from a physician's message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "ISO date YYYY-MM-DD, same as start if a single day"},
            "request_type": {
                "type": "string",
                "enum": [t.value for t in TimeOffType],
            },
            "priority": {
                "type": "string",
                "enum": [p.value for p in RequestPriority],
                "description": "'must' if the message conveys this is non-negotiable, else 'preferred'",
            },
            "reason": {"type": "string"},
        },
        "required": ["start_date", "end_date", "request_type", "priority"],
    },
}


@dataclass
class ParsedTimeOff:
    start_date: date
    end_date: date
    request_type: TimeOffType
    priority: RequestPriority
    reason: str | None
    parsed_by: str  # "ai" | "fallback"


def parse_time_off_text(text: str, reference_date: date | None = None) -> ParsedTimeOff:
    client = get_client()
    if client is not None:
        try:
            return _parse_with_claude(client, text)
        except Exception:
            pass  # fall through to the deterministic parser below
    return _parse_fallback(text, reference_date or date.today())


def _parse_with_claude(client, text: str) -> ParsedTimeOff:
    from app.config import get_settings

    settings = get_settings()
    today = date.today().isoformat()
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=512,
        system=(
            f"Today's date is {today}. Extract a structured time-off request from the "
            "physician's message using the extract_time_off_request tool. Resolve relative "
            "dates ('next week', 'Christmas') against today's date."
        ),
        tools=[_EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "extract_time_off_request"},
        messages=[{"role": "user", "content": text}],
    )
    tool_use = next(b for b in message.content if b.type == "tool_use")
    data = tool_use.input
    return ParsedTimeOff(
        start_date=date.fromisoformat(data["start_date"]),
        end_date=date.fromisoformat(data["end_date"]),
        request_type=TimeOffType(data["request_type"]),
        priority=RequestPriority(data["priority"]),
        reason=data.get("reason"),
        parsed_by="ai",
    )


_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_MUST_WORDS = ("must", "need", "required", "non-negotiable", "critical", "important", "have to")
_TYPE_WORDS = {
    TimeOffType.VACATION: ("vacation", "trip", "travel", "holiday"),
    TimeOffType.CME: ("cme", "conference", "course", "training"),
    TimeOffType.SICK: ("sick", "illness", "surgery", "medical"),
    TimeOffType.PERSONAL: ("personal", "family", "wedding", "birth"),
}


def _parse_fallback(text: str, today: date) -> ParsedTimeOff:
    """No LLM configured: extract ISO dates if present, otherwise default to
    a single day one week out so the request is at least created and an
    admin can correct it, and keyword-match type/priority."""
    lowered = text.lower()
    found_dates = [date.fromisoformat(d) for d in _DATE_RE.findall(text)]
    if len(found_dates) >= 2:
        start, end = sorted(found_dates)[0], sorted(found_dates)[-1]
    elif len(found_dates) == 1:
        start = end = found_dates[0]
    else:
        start = end = today + timedelta(days=7)

    request_type = TimeOffType.OTHER
    for t, words in _TYPE_WORDS.items():
        if any(w in lowered for w in words):
            request_type = t
            break

    priority = RequestPriority.MUST if any(w in lowered for w in _MUST_WORDS) else RequestPriority.PREFERRED

    return ParsedTimeOff(
        start_date=start,
        end_date=end,
        request_type=request_type,
        priority=priority,
        reason=text.strip()[:500],
        parsed_by="fallback",
    )
