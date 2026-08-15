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
