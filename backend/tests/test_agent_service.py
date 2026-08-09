"""Dependency-free self-check for the pure logic in
`app.services.agent_service` — no network/DB/Anthropic API call
required. Run from `backend/`:

    python -m tests.test_agent_service

`generate_morning_briefing()` and `draft_customer_communication()` still
touch Supabase and/or the Anthropic API for real and are exercised live
instead — see docs/BUSINESS_INTELLIGENCE_LAYER.md "Verification".
`ask_operations_question()` is now covered offline too (the
`ask_operations_question_*` tests below): briefing_service, rag_service,
and the Anthropic client are mocked at their exact call boundary, but the
real prompt-formatting and response-handling code inside the function
still runs, against fixed inputs. Everything else here is the
JSON-response parsing this module builds its structured outputs on.
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.services import agent_service
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


# --- ask_operations_question() orchestration, mocked at the ----------------
# briefing_service/rag_service/Claude boundary only. Everything in between
# (is_configured(), the prompt f-string, unpacking the response) is real.


def test_ask_operations_question_incorporates_briefing_and_knowledge_into_the_model_request():
    fake_briefing = {
        "todaysOrders": 7,
        "todaysRevenue": 412.50,
        "forecast": {
            "predictedOrders": 12,
            "predictedRevenue": 890.0,
            "workloadLevel": "High",
            "confidence": 82,
            "reason": "Based on last week's Saturday volume.",
        },
        "pendingNotifications": {"total": 3},
        "highPriorityOrders": [
            {
                "customerName": "Amelia Novak",
                "templateName": "Rose Gold Tier Cake",
                "status": "in_progress",
                "reason": "Pickup due today",
            }
        ],
    }
    fake_chunks = [
        {
            "title": "Bakery Operations Manual",
            "content": "Add a second baker above 10 predicted orders.",
            "source_file": "bakery_operations_manual.md",
        }
    ]
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Yes, staff up for tomorrow's High workload.")]
    )

    with (
        patch.object(agent_service.briefing_service, "get_daily_briefing", return_value=fake_briefing),
        patch.object(agent_service.rag_service, "retrieve", return_value=fake_chunks) as mock_retrieve,
        patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
    ):
        mock_anthropic_cls.return_value.messages.create.return_value = fake_response
        result = agent_service.ask_operations_question("Are we staffed for tomorrow?")

    mock_retrieve.assert_called_once_with("Are we staffed for tomorrow?", top_k=4)

    sent_prompt = mock_anthropic_cls.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
    # Live operational/briefing context reached the model request.
    assert "7 orders" in sent_prompt
    assert "$412.50" in sent_prompt
    assert "12 orders" in sent_prompt
    assert "High workload" in sent_prompt
    assert "Amelia Novak" in sent_prompt
    # Retrieved bakery knowledge reached the model request too.
    assert "Bakery Operations Manual" in sent_prompt
    assert "Add a second baker above 10 predicted orders." in sent_prompt

    assert result["answer"] == "Yes, staff up for tomorrow's High workload."  # mocked response handled correctly
    assert result["sources"] == [{"title": "Bakery Operations Manual", "sourceFile": "bakery_operations_manual.md"}]


def test_ask_operations_question_falls_back_cleanly_when_not_configured():
    fake_briefing = {
        "todaysOrders": 0,
        "todaysRevenue": 0.0,
        "forecast": {"predictedOrders": 0, "predictedRevenue": 0.0, "workloadLevel": "Low", "confidence": 50, "reason": "x"},
        "pendingNotifications": {"total": 0},
        "highPriorityOrders": [],
    }
    with (
        patch.object(agent_service.briefing_service, "get_daily_briefing", return_value=fake_briefing),
        patch.object(agent_service.rag_service, "retrieve", return_value=[]) as mock_retrieve,
        patch.object(agent_service.settings, "anthropic_api_key", None),
    ):
        result = agent_service.ask_operations_question("Anything to know?")

    mock_retrieve.assert_called_once_with("Anything to know?", top_k=4)
    assert "isn't available right now" in result["answer"]
    assert result["sources"] == []


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
