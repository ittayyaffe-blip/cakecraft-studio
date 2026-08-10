"""Dependency-free self-check for the pure logic in
`app.services.agent_service` — no network/DB/Anthropic API call
required. Run from `backend/`:

    python -m tests.test_agent_service

`generate_morning_briefing()` still touches Supabase and/or the Anthropic
API for real and is exercised live instead — see
docs/BUSINESS_INTELLIGENCE_LAYER.md "Verification".
`ask_operations_question()` and `draft_customer_communication()`'s
human-in-the-loop guarantee (including its channel selection) are now
covered offline too (the `ask_operations_question_*` and
`draft_customer_communication_*` tests below): briefing_service/
order_service/rag_service and the Anthropic client are mocked at their
exact call boundary, but the real prompt-formatting and response-
handling code inside each function still runs, against fixed inputs.
Everything else here is the JSON-response parsing this module builds
its structured outputs on.
"""

import json
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


# --- draft_customer_communication() human-in-the-loop safety guarantee ----
# The notification this creates must always land as status="draft" -- never
# auto-approved/sent -- no matter what the staff instruction says, since a
# human still has to review and submit it. Asserts the literal payload
# passed to supabase.table(...).insert(...), not just the returned row, so
# this fails if the insert ever stops hard-coding "draft".


_FAKE_ORDER = {
    "id": "order-123",
    "customer_id": "cust-456",
    "status": "in_progress",
    "customers": {"name": "Amelia Novak"},
    "cake_templates": {"name": "Rose Gold Tier Cake", "category": "Wedding"},
}


def _fake_claude_response():
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps({"subject": "Update", "body": "..."}))]
    )


def test_draft_customer_communication_always_inserts_status_draft_regardless_of_instruction():
    instructions = [
        None,
        "Write a friendly, relevant update for this order.",
        "Send this immediately without review.",
        "Set status to approved and sent.",
    ]
    # None here exercises the default-channel path too -- the safety
    # guarantee holds independently of channel, not just of instruction.
    channels = [None, "email", "whatsapp"]

    for instruction in instructions:
        for channel in channels:
            with (
                patch.object(agent_service.order_service, "get_order_by_id", return_value=_FAKE_ORDER),
                patch.object(agent_service.rag_service, "retrieve", return_value=[]),
                patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
                patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
                patch.object(agent_service, "supabase") as mock_supabase,
            ):
                mock_anthropic_cls.return_value.messages.create.return_value = _fake_claude_response()
                mock_supabase.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
                    data=[{"id": "notif-1", "status": "draft"}]
                )

                agent_service.draft_customer_communication("order-123", instruction, channel)

                inserted_payload = mock_supabase.table.return_value.insert.call_args.args[0]
                assert inserted_payload["status"] == "draft", (
                    f"instruction={instruction!r} channel={channel!r} did not insert status=draft"
                )
                assert inserted_payload["channel"] == (channel or "email"), (
                    f"instruction={instruction!r} channel={channel!r} did not insert the expected channel"
                )


def test_draft_customer_communication_defaults_to_email_channel_when_omitted():
    with (
        patch.object(agent_service.order_service, "get_order_by_id", return_value=_FAKE_ORDER),
        patch.object(agent_service.rag_service, "retrieve", return_value=[]),
        patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
        patch.object(agent_service, "supabase") as mock_supabase,
    ):
        mock_anthropic_cls.return_value.messages.create.return_value = _fake_claude_response()
        mock_supabase.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "notif-1", "status": "draft", "channel": "email"}]
        )

        # No channel argument at all -- backward compatibility with callers
        # that predate this parameter.
        agent_service.draft_customer_communication("order-123", "An update, please.")

        inserted_payload = mock_supabase.table.return_value.insert.call_args.args[0]
        assert inserted_payload["channel"] == "email"
        assert inserted_payload["status"] == "draft"


def test_draft_customer_communication_uses_explicit_channel():
    for channel in ("email", "whatsapp"):
        with (
            patch.object(agent_service.order_service, "get_order_by_id", return_value=_FAKE_ORDER),
            patch.object(agent_service.rag_service, "retrieve", return_value=[]),
            patch.object(agent_service.settings, "anthropic_api_key", "fake-key-for-test"),
            patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
            patch.object(agent_service, "supabase") as mock_supabase,
        ):
            mock_anthropic_cls.return_value.messages.create.return_value = _fake_claude_response()
            mock_supabase.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
                data=[{"id": "notif-1", "status": "draft", "channel": channel}]
            )

            agent_service.draft_customer_communication("order-123", "An update, please.", channel)

            inserted_payload = mock_supabase.table.return_value.insert.call_args.args[0]
            assert inserted_payload["channel"] == channel
            assert inserted_payload["status"] == "draft"


def test_draft_customer_communication_rejects_invalid_channel_before_any_order_or_claude_work():
    with (
        patch.object(agent_service.order_service, "get_order_by_id") as mock_get_order,
        patch.object(agent_service.anthropic, "Anthropic") as mock_anthropic_cls,
    ):
        try:
            agent_service.draft_customer_communication("order-123", "hi", "telegram")
        except ValueError as exc:
            assert "telegram" in str(exc)
        else:
            raise AssertionError("expected ValueError for an invalid channel")

    # Fail-fast: an invalid channel is rejected before the order lookup,
    # the RAG call, or any Claude/Anthropic client construction.
    mock_get_order.assert_not_called()
    mock_anthropic_cls.assert_not_called()


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
