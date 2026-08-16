"""Dependency-free self-check for bakery_manager_service.py -- the AI
Bakery Manager's planning/execution logic. No network/DB/Anthropic call;
every external boundary (order_service, notification_service,
briefing_service, rag_service, agent_service._claude/is_configured,
audit_service.record_event) mocked at its exact call site -- the real
classification/validation/execution logic inside the module runs for
real against fixed inputs. Run from `backend/`:

    python -m tests.test_bakery_manager_service
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.services import bakery_manager_service as bms

_ADMIN_ID = "staff-1"
_TODAY = datetime.now(timezone.utc).date()

_ORDER_PICKUP_SOON = {
    "id": "order-1", "customer_id": "cust-1", "status": "confirmed",
    "pickup_date": (_TODAY + timedelta(days=1)).isoformat(),
    "customers": {"name": "Jane Doe"}, "cake_templates": {"name": "Rose Cake", "category": "Birthday"},
}
_ORDER_PICKUP_FAR = {
    "id": "order-2", "customer_id": "cust-2", "status": "confirmed",
    "pickup_date": (_TODAY + timedelta(days=10)).isoformat(),
    "customers": {"name": "Amir Cohen"}, "cake_templates": {"name": "Gold Cake", "category": "Wedding"},
}
_ORDER_NO_PICKUP = {
    "id": "order-3", "customer_id": "cust-3", "status": "confirmed", "pickup_date": None,
    "customers": {"name": "Mei Chen"}, "cake_templates": {"name": "Blue Cake", "category": "Corporate"},
}

_FAKE_BRIEFING = {
    "todaysOrders": 3, "todaysRevenue": 150.0,
    "forecast": {"predictedOrders": 5, "predictedRevenue": 400.0, "workloadLevel": "High", "confidence": 60, "reason": "Busy day."},
    "highPriorityOrders": [], "pendingNotifications": {"total": 0, "items": []},
}


def _claude_plan_json(**overrides):
    payload = {
        "operationalSummary": "A normal day.",
        "proposedActions": [],
        "recommendations": {"staffing": [], "inventory": [], "workload": [], "production": []},
        "exceptions": [],
    }
    payload.update(overrides)
    return json.dumps(payload)


def _run_preview(claude_json, *, confirmed=None, in_progress=None, ready=None, configured=True):
    confirmed = _ORDER_PICKUP_SOON.__class__ and (confirmed if confirmed is not None else [_ORDER_PICKUP_SOON])
    in_progress = in_progress or []
    ready = ready or []

    def fake_list_orders(status=None, page_size=100):
        return {"items": {"confirmed": confirmed, "in_progress": in_progress, "ready": ready}.get(status, [])}

    with (
        patch.object(bms, "record_event") as mock_audit,
        patch.object(bms.briefing_service, "get_daily_briefing", return_value=_FAKE_BRIEFING),
        patch.object(bms.order_service, "list_orders", side_effect=fake_list_orders),
        patch.object(bms.rag_service, "retrieve", return_value=[{"title": "Production Workflow", "content": "...", "source_file": "production_workflow.md"}]),
        patch.object(bms.agent_service, "is_configured", return_value=configured),
        patch.object(bms.agent_service, "_claude", return_value=claude_json),
        patch.object(bms.order_service, "get_order_by_id", side_effect=lambda oid: next(
            (o for o in confirmed + in_progress + ready if o["id"] == oid), None
        )),
    ):
        plan = bms.get_preview_plan(_ADMIN_ID)
    return plan, mock_audit


# --- PREVIEW -----------------------------------------------------------


def test_preview_returns_a_plan_with_run_id_and_summary():
    plan, mock_audit = _run_preview(_claude_plan_json(operationalSummary="Quiet day."))
    assert plan["mode"] == "preview"
    assert plan["runId"]
    assert plan["operationalSummary"] == "Quiet day."
    mock_audit.assert_called_once()
    assert mock_audit.call_args.kwargs["action"] == "agent.plan_generated"


def test_preview_performs_no_order_or_notification_writes():
    # order_service.update_order_status / notification_service.* are never
    # patched as "in use" here -- if get_preview_plan called either, this
    # test would need to mock them; asserting they were never even
    # imported-and-called proves Preview really is read-only.
    with (
        patch.object(bms.order_service, "update_order_status") as mock_update,
        patch.object(bms.notification_service, "create_notification_for_order_event") as mock_notify,
    ):
        _run_preview(_claude_plan_json())
        mock_update.assert_not_called()
        mock_notify.assert_not_called()


def test_unknown_claude_action_type_is_forced_unsafe():
    plan, _ = _run_preview(_claude_plan_json(proposedActions=[
        {"actionType": "delete_all_orders", "orderId": "order-1", "reason": "why not", "confidence": 99}
    ]))
    action = plan["proposedActions"][0]
    assert action["safeToExecute"] is False
    assert action["requiresManagerAttention"] is True


def test_missing_pickup_date_makes_advance_to_in_progress_unsafe_and_flagged():
    plan, _ = _run_preview(
        _claude_plan_json(proposedActions=[
            {"actionType": "advance_to_in_progress", "orderId": "order-3", "reason": "start it", "confidence": 80}
        ]),
        confirmed=[_ORDER_NO_PICKUP],
    )
    action = plan["proposedActions"][0]
    assert action["safeToExecute"] is False
    # Deterministic exception is always present, regardless of what Claude said
    exception_order_ids = [e["orderId"] for e in plan["exceptions"]]
    assert "order-3" in exception_order_ids
    missing_pickup = next(e for e in plan["exceptions"] if e["orderId"] == "order-3")
    assert missing_pickup["type"] == "missing_pickup_date"


def test_pickup_date_too_far_out_is_not_yet_eligible():
    plan, _ = _run_preview(
        _claude_plan_json(proposedActions=[
            {"actionType": "advance_to_in_progress", "orderId": "order-2", "reason": "start it", "confidence": 80}
        ]),
        confirmed=[_ORDER_PICKUP_FAR],
    )
    assert plan["proposedActions"][0]["safeToExecute"] is False


def test_pickup_date_within_window_is_eligible():
    plan, _ = _run_preview(
        _claude_plan_json(proposedActions=[
            {"actionType": "advance_to_in_progress", "orderId": "order-1", "reason": "start it", "confidence": 80}
        ]),
        confirmed=[_ORDER_PICKUP_SOON],
    )
    assert plan["proposedActions"][0]["safeToExecute"] is True


def test_advance_to_ready_and_completed_are_always_recommendation_only():
    plan, _ = _run_preview(_claude_plan_json(proposedActions=[
        {"actionType": "advance_to_ready", "orderId": "order-x", "reason": "looks done", "confidence": 90},
        {"actionType": "advance_to_completed", "orderId": "order-y", "reason": "picked up", "confidence": 90},
    ]))
    for action in plan["proposedActions"]:
        assert action["safeToExecute"] is False


def test_never_autonomous_action_types_are_not_in_the_allowed_vocabulary():
    for forbidden in ("send_email", "process_payment", "cancel_order", "change_price", "approve_allergy_exception"):
        assert forbidden not in bms._ALL_KNOWN_ACTION_TYPES


def test_ai_unconfigured_returns_a_clean_empty_plan_not_an_error():
    plan, mock_audit = _run_preview(_claude_plan_json(), configured=False)
    assert plan["proposedActions"] == []
    assert "AI Bakery Manager couldn't generate a plan" in plan["operationalSummary"]
    mock_audit.assert_called_once()


def test_claude_failure_falls_back_to_a_clean_plan_not_a_crash():
    with (
        patch.object(bms, "record_event"),
        patch.object(bms.briefing_service, "get_daily_briefing", return_value=_FAKE_BRIEFING),
        patch.object(bms.order_service, "list_orders", return_value={"items": []}),
        patch.object(bms.rag_service, "retrieve", return_value=[]),
        patch.object(bms.agent_service, "is_configured", return_value=True),
        patch.object(bms.agent_service, "_claude", side_effect=Exception("timeout")),
    ):
        plan = bms.get_preview_plan(_ADMIN_ID)
    assert plan["proposedActions"] == []


def test_preview_claude_call_uses_a_longer_timeout_and_output_budget_than_the_shared_default():
    # Two real production failures this locks in the fix for: (1) this
    # prompt's Claude call was timing out at the 12.0s default every other
    # caller keeps (see test_agent_service.test_claude_default_timeout_and_
    # retries_are_exactly_unchanged), fixed with timeout=30.0; (2) once
    # that let the call complete, it still hit stop_reason=max_tokens at
    # 1500 and got truncated mid-JSON on a normal-sized order backlog,
    # fixed with max_tokens=3000. max_retries stays at the shared default
    # (1) -- neither fix touches retry behavior.
    with (
        patch.object(bms, "record_event"),
        patch.object(bms.briefing_service, "get_daily_briefing", return_value=_FAKE_BRIEFING),
        patch.object(bms.order_service, "list_orders", return_value={"items": []}),
        patch.object(bms.rag_service, "retrieve", return_value=[]),
        patch.object(bms.agent_service, "is_configured", return_value=True),
        patch.object(bms.agent_service, "_claude", return_value=_claude_plan_json()) as mock_claude,
    ):
        bms.get_preview_plan(_ADMIN_ID)

    assert mock_claude.call_args.kwargs["timeout"] == 30.0
    assert mock_claude.call_args.kwargs["max_tokens"] == 3000
    assert "max_retries" not in mock_claude.call_args.kwargs  # inherits the shared default (1), not widened


def test_planning_prompt_only_lists_eligible_confirmed_orders_not_the_full_backlog():
    # Third live production failure's root cause: the prompt used to list
    # EVERY confirmed order (eligible or not), inviting Claude to enumerate
    # far more than the real executable candidate pool. Now only orders
    # production_start_eligible=True get a line.
    context = {
        "briefing": _FAKE_BRIEFING,
        "confirmed_orders": [
            {**_ORDER_PICKUP_SOON, "_productionStartEligible": True, "_evidence": ["due soon"]},
            {**_ORDER_PICKUP_FAR, "_productionStartEligible": False, "_evidence": ["too far out"]},
            {**_ORDER_NO_PICKUP, "_productionStartEligible": False, "_evidence": ["no pickup date"]},
        ],
        "in_progress_orders": [], "ready_orders": [], "priority_candidates": [], "knowledge": [],
    }
    prompt = bms._build_planning_prompt(context)
    assert _ORDER_PICKUP_SOON["id"] in prompt
    assert _ORDER_PICKUP_FAR["id"] not in prompt
    assert _ORDER_NO_PICKUP["id"] not in prompt


def test_order_summary_line_shows_guest_count_as_context_when_available():
    # Servings + Event Pricing: purely informational -- never read by
    # anything that decides safety/eligibility.
    order_with_guests = {
        **_ORDER_PICKUP_SOON,
        "configuration": {"guestCount": 60, "cakeSize": {"name": "Event"}},
    }
    line = bms._order_summary_line(order_with_guests)
    assert "guests=60" in line
    assert "Event" in line


def test_order_summary_line_omits_guest_count_when_not_recorded():
    # Real orders may not have it (historical/no-guest_count callers) --
    # never invented, matching Back Office's own "Not recorded" posture.
    line = bms._order_summary_line(_ORDER_PICKUP_SOON)
    assert "guests=" not in line


def test_planning_prompt_renders_only_the_precomputed_priority_candidates():
    # Bounding itself now happens upstream in _priority_flagged_candidates
    # (see its own dedicated tests below) -- _build_planning_prompt just
    # renders whatever context["priority_candidates"] already is, and must
    # never fall back to the full in_progress/ready lists if that's bigger.
    many_in_progress = [{**_ORDER_PICKUP_SOON, "id": f"noisy-{i}"} for i in range(20)]
    context = {
        "briefing": _FAKE_BRIEFING,
        "confirmed_orders": [],
        "in_progress_orders": many_in_progress, "ready_orders": [],
        "priority_candidates": [{**_ORDER_PICKUP_SOON, "id": "urgent-1", "_priority": "CRITICAL", "_priorityReason": "Pickup is today."}],
        "knowledge": [],
    }
    prompt = bms._build_planning_prompt(context)
    assert "urgent-1" in prompt
    assert "noisy-0" not in prompt  # the unbounded backlog never reaches the prompt


def test_priority_flagged_candidates_bounds_to_critical_and_high_only():
    orders = [
        {**_ORDER_PICKUP_SOON, "id": "high-1", "status": "in_progress"},  # 1 day out -> HIGH
        {**_ORDER_PICKUP_FAR, "id": "normal-1", "status": "ready"},  # far out -> NORMAL/LOW, excluded
        {**_ORDER_NO_PICKUP, "id": "needs-info-1", "status": "in_progress"},  # missing date -> excluded (an exception, not a priority)
    ]
    candidates = bms._priority_flagged_candidates(orders)
    ids = [o["id"] for o in candidates]
    assert "high-1" in ids
    assert "normal-1" not in ids
    assert "needs-info-1" not in ids


def test_priority_flagged_candidates_respects_the_limit_and_critical_first_order():
    critical = {**_ORDER_PICKUP_SOON, "id": "crit-1", "status": "ready", "pickup_date": _TODAY.isoformat()}
    high_orders = [{**_ORDER_PICKUP_SOON, "id": f"high-{i}", "status": "in_progress"} for i in range(6)]
    candidates = bms._priority_flagged_candidates(high_orders + [critical], limit=5)
    assert len(candidates) == 5
    assert candidates[0]["id"] == "crit-1"  # CRITICAL sorts before HIGH regardless of list order


def test_claude_timeout_still_surfaces_the_deterministic_pickup_date_exceptions():
    # The exact production failure mode: Claude times out, but the
    # deterministic exception list (never dependent on Claude succeeding)
    # must still reach the manager -- proven here with anthropic's own
    # timeout exception type, not a generic one.
    import anthropic

    with (
        patch.object(bms, "record_event") as mock_audit,
        patch.object(bms.briefing_service, "get_daily_briefing", return_value=_FAKE_BRIEFING),
        patch.object(bms.order_service, "list_orders", side_effect=lambda status=None, page_size=100: {
            "items": [_ORDER_NO_PICKUP] if status == "confirmed" else []
        }),
        patch.object(bms.rag_service, "retrieve", return_value=[]),
        patch.object(bms.agent_service, "is_configured", return_value=True),
        patch.object(bms.agent_service, "_claude", side_effect=anthropic.APITimeoutError(request=None)),
    ):
        plan = bms.get_preview_plan(_ADMIN_ID)

    assert plan["proposedActions"] == []
    assert any(e["type"] == "missing_pickup_date" and e["orderId"] == "order-3" for e in plan["exceptions"])
    assert mock_audit.call_args.kwargs["after"]["reason"] == "ai_call_failed"


def _run_preview_with_raw_claude_text(raw_text, *, confirmed=None):
    confirmed = confirmed if confirmed is not None else [_ORDER_NO_PICKUP]
    with (
        patch.object(bms, "record_event") as mock_audit,
        patch.object(bms, "logger") as mock_logger,
        patch.object(bms.briefing_service, "get_daily_briefing", return_value=_FAKE_BRIEFING),
        patch.object(bms.order_service, "list_orders", side_effect=lambda status=None, page_size=100: {
            "items": confirmed if status == "confirmed" else []
        }),
        patch.object(bms.rag_service, "retrieve", return_value=[]),
        patch.object(bms.agent_service, "is_configured", return_value=True),
        patch.object(bms.agent_service, "_claude", return_value=raw_text),
    ):
        plan = bms.get_preview_plan(_ADMIN_ID)
    return plan, mock_audit, mock_logger


def test_truncated_claude_response_fails_closed_with_no_executable_actions():
    # The exact second production failure: Claude answers (no exception --
    # a real, successful API call) but gets cut off mid-JSON before the
    # outer object closes. This must fail closed, not attempt to salvage
    # a partial plan.
    truncated = (
        '{"operationalSummary": "Busy day.", "proposedActions": '
        '[{"actionType": "advance_to_in_progress", "orderId": "order-1", "reason": "go'
    )  # cut off mid-string, no closing braces at all -- exactly the shape observed live
    plan, mock_audit, _ = _run_preview_with_raw_claude_text(truncated)

    assert plan["proposedActions"] == []  # nothing partially parsed, nothing executable
    assert plan["operationalSummary"] == "AI Bakery Manager couldn't generate a plan right now — the manual Back Office remains fully available."
    assert mock_audit.call_args.kwargs["after"]["reason"] == "ai_call_failed"
    # Deterministic exceptions never depend on Claude succeeding.
    assert any(e["type"] == "missing_pickup_date" and e["orderId"] == "order-3" for e in plan["exceptions"])


def test_parse_failure_logs_a_safe_diagnostic_warning_without_sensitive_content():
    truncated = '{"operationalSummary": "Busy day.", "proposedActions": [{"actionType": "advance'
    _plan, _audit, mock_logger = _run_preview_with_raw_claude_text(truncated)

    mock_logger.warning.assert_called_once()
    logged = " ".join(str(a) for a in mock_logger.warning.call_args.args)
    # Useful metadata present...
    assert "order-3" not in logged and "Mei Chen" not in logged  # ...but no order/customer content
    assert str(len(truncated)) in logged  # response_chars metadata is present
    mock_logger.exception.assert_not_called()  # this path never raised -- exception logging is a separate branch


# --- AI BOUNDARY ---------------------------------------------------------


def test_claude_safe_to_execute_opinion_is_never_read_or_trusted():
    # Even if Claude's own JSON included a safeToExecute-like field, the
    # schema/prompt never asks for one and _classify_action never reads
    # it -- proven here by injecting one anyway and confirming the
    # application's own (correctly negative) computation wins.
    plan, _ = _run_preview(
        _claude_plan_json(proposedActions=[
            {"actionType": "advance_to_in_progress", "orderId": "order-3", "reason": "go", "confidence": 99, "safeToExecute": True}
        ]),
        confirmed=[_ORDER_NO_PICKUP],
    )
    assert plan["proposedActions"][0]["safeToExecute"] is False


def test_claude_cannot_propose_a_transition_out_of_the_allowed_graph():
    plan, _ = _run_preview(_claude_plan_json(proposedActions=[
        {"actionType": "advance_to_in_progress", "orderId": "order-completed", "reason": "go", "confidence": 90}
    ]))
    with patch.object(bms.order_service, "get_order_by_id", return_value={"id": "order-completed", "status": "completed", "pickup_date": _TODAY.isoformat()}):
        result = bms._classify_action({"actionType": "advance_to_in_progress", "orderId": "order-completed", "reason": "go", "confidence": 90})
    assert result["safeToExecute"] is False


def test_advance_to_in_progress_evidence_includes_the_shared_priority_label():
    # Part of Pickup Date + Order Priority, Phase 2: the same priority
    # label/reason the Back Office and RAG use is surfaced as evidence --
    # informational only, never read back as an authorization (safe is
    # still decided entirely by _revalidate_order_for_action above it).
    with patch.object(bms.order_service, "get_order_by_id", return_value=_ORDER_PICKUP_SOON):
        result = bms._classify_action({"actionType": "advance_to_in_progress", "orderId": "order-1", "reason": "go", "confidence": 90})
    assert result["safeToExecute"] is True
    assert any(line.startswith("Priority: HIGH") for line in result["evidence"])


def test_classified_action_carries_the_structured_priority_field():
    # The ProposedAction.priority field (not just the evidence line) --
    # used by the frontend for a real badge, not string-parsed evidence.
    # Stays exactly what priority_service returns: None for the missing-
    # pickup-date case, never a "NEEDS INFO" placeholder string (that
    # wording is only ever in the human-readable evidence text).
    with patch.object(bms.order_service, "get_order_by_id", return_value=_ORDER_PICKUP_SOON):
        result = bms._classify_action({"actionType": "advance_to_in_progress", "orderId": "order-1", "reason": "go", "confidence": 90})
    assert result["priority"] == "HIGH"

    with patch.object(bms.order_service, "get_order_by_id", return_value=_ORDER_NO_PICKUP):
        result = bms._classify_action({"actionType": "advance_to_in_progress", "orderId": "order-3", "reason": "go", "confidence": 90})
    assert result["priority"] is None


def test_priority_service_is_the_one_source_computing_evidence_not_a_reimplementation():
    # Proves delegation, not a parallel calculation: patching
    # priority_service.compute_priority changes what shows up in the
    # evidence, confirming _classify_action actually calls it rather than
    # deriving the label some other way.
    fake_result = {"priority": "CRITICAL", "reason": "Patched reason for this test.", "manager_attention": True}
    with (
        patch.object(bms.order_service, "get_order_by_id", return_value=_ORDER_PICKUP_SOON),
        patch.object(bms.priority_service, "compute_priority", return_value=fake_result) as mock_compute,
    ):
        result = bms._classify_action({"actionType": "advance_to_in_progress", "orderId": "order-1", "reason": "go", "confidence": 90})
    mock_compute.assert_called_once_with(_ORDER_PICKUP_SOON)
    assert any("Patched reason for this test." in line for line in result["evidence"])


# --- EXECUTE ---------------------------------------------------------------


def _fresh_confirmed_order():
    return {**_ORDER_PICKUP_SOON}


def test_selected_safe_action_executes_through_the_real_service():
    order = _fresh_confirmed_order()
    with (
        patch.object(bms, "record_event") as mock_audit,
        patch.object(bms.order_service, "get_order_by_id", return_value=order),
        patch.object(bms.order_service, "update_order_status", return_value={**order, "status": "in_progress"}) as mock_update,
        patch.object(bms.notification_service, "create_notification_for_order_event", return_value={"id": "notif-1"}) as mock_notify,
    ):
        results = bms.execute_plan(_ADMIN_ID, "run-1", [
            {"actionId": "a-1", "actionType": "advance_to_in_progress", "orderId": "order-1"}
        ])
    assert results[0]["success"] is True
    assert results[0]["notificationId"] == "notif-1"
    mock_update.assert_called_once_with("order-1", "in_progress", current_status="confirmed")
    mock_notify.assert_called_once()
    assert mock_audit.call_args.kwargs["action"] == "agent.action_executed"


def test_stale_state_is_rejected_not_executed():
    # Order moved to in_progress by someone else between Preview and Execute.
    with (
        patch.object(bms, "record_event") as mock_audit,
        patch.object(bms.order_service, "get_order_by_id", return_value={**_ORDER_PICKUP_SOON, "status": "in_progress"}),
        patch.object(bms.order_service, "update_order_status") as mock_update,
    ):
        results = bms.execute_plan(_ADMIN_ID, "run-1", [
            {"actionId": "a-1", "actionType": "advance_to_in_progress", "orderId": "order-1"}
        ])
    assert results[0]["success"] is False
    mock_update.assert_not_called()
    assert mock_audit.call_args.kwargs["action"] == "agent.action_rejected"


def test_invalid_transition_target_is_rejected():
    with (
        patch.object(bms, "record_event"),
        patch.object(bms.order_service, "get_order_by_id", return_value={**_ORDER_PICKUP_SOON, "status": "completed"}),
        patch.object(bms.order_service, "update_order_status") as mock_update,
    ):
        results = bms.execute_plan(_ADMIN_ID, "run-1", [
            {"actionId": "a-1", "actionType": "advance_to_in_progress", "orderId": "order-1"}
        ])
    assert results[0]["success"] is False
    mock_update.assert_not_called()


def test_unsafe_action_missing_pickup_date_is_rejected_at_execute_too():
    with (
        patch.object(bms, "record_event"),
        patch.object(bms.order_service, "get_order_by_id", return_value=_ORDER_NO_PICKUP),
        patch.object(bms.order_service, "update_order_status") as mock_update,
    ):
        results = bms.execute_plan(_ADMIN_ID, "run-1", [
            {"actionId": "a-1", "actionType": "advance_to_in_progress", "orderId": "order-3"}
        ])
    assert results[0]["success"] is False
    mock_update.assert_not_called()


def test_unknown_action_type_is_rejected_before_any_service_call():
    with (
        patch.object(bms, "record_event") as mock_audit,
        patch.object(bms.order_service, "update_order_status") as mock_update,
    ):
        results = bms.execute_plan(_ADMIN_ID, "run-1", [
            {"actionId": "a-1", "actionType": "cancel_order", "orderId": "order-1"}
        ])
    assert results[0]["success"] is False
    mock_update.assert_not_called()
    assert mock_audit.call_args.kwargs["action"] == "agent.action_rejected"


def test_duplicate_execution_of_the_same_action_stays_safe():
    order = _fresh_confirmed_order()
    with (
        patch.object(bms, "record_event"),
        patch.object(bms.order_service, "get_order_by_id", return_value=order),
        patch.object(bms.order_service, "update_order_status", return_value={**order, "status": "in_progress"}),
        patch.object(bms.notification_service, "create_notification_for_order_event", return_value={"id": "notif-1"}),
    ):
        first = bms.execute_plan(_ADMIN_ID, "run-1", [{"actionId": "a-1", "actionType": "advance_to_in_progress", "orderId": "order-1"}])
    assert first[0]["success"] is True

    # Second click: the order is now genuinely in_progress -- the same
    # revalidation that caught staleness above correctly rejects the repeat.
    with (
        patch.object(bms, "record_event"),
        patch.object(bms.order_service, "get_order_by_id", return_value={**order, "status": "in_progress"}),
        patch.object(bms.order_service, "update_order_status") as mock_update_2,
    ):
        second = bms.execute_plan(_ADMIN_ID, "run-1", [{"actionId": "a-1", "actionType": "advance_to_in_progress", "orderId": "order-1"}])
    assert second[0]["success"] is False
    mock_update_2.assert_not_called()


def test_notification_draft_creation_is_not_duplicated():
    order = {**_ORDER_PICKUP_SOON}
    with (
        patch.object(bms, "record_event"),
        patch.object(bms.order_service, "get_order_by_id", return_value=order),
        patch.object(bms.notification_service, "create_notification_for_order_event", return_value={"id": "notif-existing"}) as mock_notify,
    ):
        results = bms.execute_plan(_ADMIN_ID, "run-1", [
            {"actionId": "a-1", "actionType": "create_customer_update_draft", "orderId": "order-1"}
        ])
    # Reuses notification_service's own (order_id, event) idempotency --
    # this call just proves the draft action calls that exact function,
    # which is independently tested for idempotency in
    # test_notification_service.py, not re-tested here.
    assert results[0]["success"] is True
    mock_notify.assert_called_once_with(order, order["status"])


def test_one_failed_action_does_not_stop_the_rest_of_the_batch():
    order = _fresh_confirmed_order()
    with (
        patch.object(bms, "record_event"),
        patch.object(bms.order_service, "get_order_by_id", side_effect=lambda oid: order if oid == "order-1" else None),
        patch.object(bms.order_service, "update_order_status", return_value={**order, "status": "in_progress"}),
        patch.object(bms.notification_service, "create_notification_for_order_event", return_value={"id": "notif-1"}),
    ):
        results = bms.execute_plan(_ADMIN_ID, "run-1", [
            {"actionId": "a-1", "actionType": "advance_to_in_progress", "orderId": "does-not-exist"},
            {"actionId": "a-2", "actionType": "advance_to_in_progress", "orderId": "order-1"},
        ])
    assert results[0]["success"] is False
    assert results[1]["success"] is True  # the second action still ran despite the first failing


def test_execute_plan_never_calls_claude():
    with (
        patch.object(bms, "record_event"),
        patch.object(bms.order_service, "get_order_by_id", return_value=_fresh_confirmed_order()),
        patch.object(bms.order_service, "update_order_status", return_value=_fresh_confirmed_order()),
        patch.object(bms.notification_service, "create_notification_for_order_event", return_value=None),
        patch.object(bms.agent_service, "_claude") as mock_claude,
    ):
        bms.execute_plan(_ADMIN_ID, "run-1", [{"actionId": "a-1", "actionType": "advance_to_in_progress", "orderId": "order-1"}])
    mock_claude.assert_not_called()


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
