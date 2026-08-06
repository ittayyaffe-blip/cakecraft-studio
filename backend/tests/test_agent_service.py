"""Dependency-free self-check for the pure logic in
`app.services.agent_service` — no network/DB/Anthropic API call
required. Run from `backend/`:

    python -m tests.test_agent_service

`generate_morning_briefing()`, `ask_operations_question()`, and
`draft_customer_communication()` all touch Supabase and/or the Anthropic
API and are exercised live instead — see
docs/BUSINESS_INTELLIGENCE_LAYER.md "Verification". Everything below is
the JSON-response parsing this module builds its structured outputs on.
"""

from app.services.agent_service import _not_configured_response, _parse_json_response


def test_parse_json_response_handles_clean_json():
    result = _parse_json_response('{"narrative": "All quiet today."}')
    assert result == {"narrative": "All quiet today."}


def test_parse_json_response_strips_markdown_code_fence():
    raw = '```json\n{"narrative": "Busy day ahead."}\n```'
    assert _parse_json_response(raw) == {"narrative": "Busy day ahead."}


def test_parse_json_response_extracts_json_from_surrounding_prose():
    raw = 'Sure, here is the briefing:\n{"narrative": "Quiet."}\nLet me know if you need more.'
    assert _parse_json_response(raw) == {"narrative": "Quiet."}


def test_parse_json_response_returns_none_for_truncated_json():
    # A response cut off mid-object (hit max_tokens) — caught live: this
    # used to silently fall back to the raw, still-truncated text as a
    # notification body. None here is what triggers the fallback path
    # instead of a crash.
    truncated = '{"subject": "Hello", "body": "Dear customer, thank you for'
    assert _parse_json_response(truncated) is None


def test_parse_json_response_returns_none_for_non_json_text():
    assert _parse_json_response("I'm not able to help with that.") is None


def test_not_configured_response_has_null_structured_fields():
    result = _not_configured_response("AI generation is not configured.")
    assert result["narrative"] == "AI generation is not configured."
    assert result["productionNotes"] is None
    assert result["staffingNotes"] is None
    assert result["inventoryNotes"] is None
    assert result["sources"] == []


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
