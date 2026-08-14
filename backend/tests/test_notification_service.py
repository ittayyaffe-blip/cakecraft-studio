"""Dependency-free self-check for the pure logic in
`app.services.notification_templates` and the transition guards in
`app.services.notification_service` — no network/DB required. Run from
`backend/`:

    python -m tests.test_notification_service

Transition functions (submit_for_approval, approve, return_to_draft, send,
update_draft_content) only reach a real Supabase call *after* their status
guard passes — every test below deliberately uses a fake notification dict
whose status makes the guard fail, so only the pure validation logic runs.
The success paths (a real DB write) are exercised live via
`fastapi.testclient.TestClient` instead — see
docs/SPRINT1_EVENT_DRIVEN_COMMUNICATION.md.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import notification_service, notification_templates
from app.services.communication.base import DeliveryResult

ORDER = {
    "id": "order-1",
    "customer_id": "cust-1",
    "customers": {"id": "cust-1", "name": "Jane Doe", "email": "jane@example.com", "phone": None},
    "cake_templates": {"name": "Ivory Three-Tier Classic"},
}


def _expect_value_error(fn) -> None:
    try:
        fn()
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError, none was raised")


def test_get_template_for_status_known_status():
    template = notification_templates.get_template_for_status("confirmed")
    assert template is not None
    assert template["event"] == "order_confirmed"


def test_get_template_for_status_unmapped_status_returns_none():
    assert notification_templates.get_template_for_status("not_a_real_status") is None


def test_get_template_for_status_pending_has_an_order_received_template():
    # Step 5: "order received" now gets the same draft -> approve -> send
    # treatment as every later transition -- this was the one status with
    # no template at all before.
    template = notification_templates.get_template_for_status("pending")
    assert template is not None
    assert template["event"] == "order_received"


def test_render_fills_customer_and_template_name():
    template = notification_templates.get_template_for_status("ready")
    rendered = notification_templates.render(template, ORDER)
    assert "Jane Doe" in rendered["body"]
    assert "Ivory Three-Tier Classic" in rendered["body"]
    assert rendered["subject"] == "Your cake is ready for pickup!"


def test_render_falls_back_when_customer_or_template_missing():
    template = notification_templates.get_template_for_status("confirmed")
    rendered = notification_templates.render(template, {})
    assert "there" in rendered["body"]
    assert "your cake" in rendered["body"]


def test_render_includes_pickup_date_when_the_order_actually_has_one():
    # Real fact in, real fact out -- never invented. Most real orders never
    # get a pickup_date set today (see render()'s own docstring), so this
    # is the "it happens to be there" path, not the default.
    template = notification_templates.get_template_for_status("confirmed")
    order_with_pickup = {**ORDER, "pickup_date": "2026-09-01"}
    rendered = notification_templates.render(template, order_with_pickup)
    assert "2026-09-01" in rendered["body"]


def test_render_omits_pickup_line_when_the_order_has_no_pickup_date():
    template = notification_templates.get_template_for_status("confirmed")
    rendered = notification_templates.render(template, ORDER)  # ORDER has no pickup_date
    assert "pickup date" not in rendered["body"].lower()


def test_render_ready_template_never_states_a_pickup_date():
    # Deliberate: "ready" stays date-free even if pickup_date is set --
    # see render()'s own docstring on why restating it here could read as
    # a future promise rather than a completed fact.
    template = notification_templates.get_template_for_status("ready")
    order_with_pickup = {**ORDER, "pickup_date": "2026-09-01"}
    rendered = notification_templates.render(template, order_with_pickup)
    assert "2026-09-01" not in rendered["body"]


def test_event_labels_cover_every_template():
    for template in notification_templates.ORDER_STATUS_EVENT_TEMPLATES.values():
        assert notification_service.get_event_label(template["event"]) == template["label"]


def test_get_event_label_falls_back_to_key_for_unknown_event():
    assert notification_service.get_event_label("some_future_event") == "some_future_event"


def test_submit_for_approval_rejects_non_draft():
    _expect_value_error(
        lambda: notification_service.submit_for_approval({"status": "sent", "id": "x"})
    )


def test_approve_rejects_non_awaiting_approval():
    _expect_value_error(lambda: notification_service.approve({"status": "draft", "id": "x"}))


def test_return_to_draft_rejects_queued():
    _expect_value_error(
        lambda: notification_service.return_to_draft({"status": "queued", "id": "x"})
    )


def test_send_rejects_non_approved():
    # Renamed nothing -- "approved" is still one of three valid starting
    # statuses (see _SEND_ALLOWED_FROM), "awaiting_approval" still isn't.
    _expect_value_error(
        lambda: notification_service.send({"status": "awaiting_approval", "id": "x"})
    )


def test_send_rejects_queued():
    _expect_value_error(lambda: notification_service.send({"status": "queued", "id": "x"}))


def test_send_rejects_already_sent():
    _expect_value_error(lambda: notification_service.send({"status": "sent", "id": "x"}))


def test_update_draft_content_rejects_non_draft():
    _expect_value_error(
        lambda: notification_service.update_draft_content(
            {"status": "approved", "id": "x", "subject": "old", "body": "old"}, "new", "new"
        )
    )


def test_update_draft_content_accepts_failed_so_it_can_be_fixed_before_a_retry():
    with patch.object(notification_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{}]
        )
        mock_supabase.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
            data={"id": "notif-4", "status": "failed", "subject": "new", "body": "new"}
        )
        result = notification_service.update_draft_content(
            {"status": "failed", "id": "notif-4", "subject": "old", "body": "old"}, "new", "new"
        )
    assert result["status"] == "failed"


# --- Simplified workflow (draft -> send -> sent/failed) --------------------


def _mock_update_and_refetch(mock_supabase, updated_row: dict) -> None:
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[updated_row]
    )
    mock_supabase.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data=updated_row
    )


def test_send_from_draft_succeeds_and_populates_sent_at():
    # No more submit-for-approval/approve step -- a human writes/edits a
    # draft, clicks Send, that's the one approval this stage needs.
    notification = {"id": "notif-1", "status": "draft", "channel": "email"}
    updated_row = {"id": "notif-1", "status": "sent", "channel": "email", "sent_at": "2026-08-11T00:00:00+00:00"}
    with (
        patch.object(notification_service, "supabase") as mock_supabase,
        patch.object(
            notification_service, "_dispatch",
            return_value=("email", DeliveryResult(success=True, provider_message_id="msg-1")),
        ),
    ):
        _mock_update_and_refetch(mock_supabase, updated_row)
        result = notification_service.send(notification)

    assert result["status"] == "sent"
    update_payload = mock_supabase.table.return_value.update.call_args.args[0]
    assert update_payload["status"] == "sent"
    assert update_payload["sent_at"]
    assert update_payload["provider_message_id"] == "msg-1"
    mock_supabase.table.return_value.insert.assert_not_called()  # no duplicate row


def test_send_delivery_failure_lands_on_failed_with_a_usable_error():
    notification = {"id": "notif-2", "status": "draft", "channel": "email"}
    updated_row = {"id": "notif-2", "status": "failed", "channel": "email"}
    with (
        patch.object(notification_service, "supabase") as mock_supabase,
        patch.object(
            notification_service, "_dispatch",
            return_value=("email", DeliveryResult(success=False, error="Network is unreachable")),
        ),
    ):
        _mock_update_and_refetch(mock_supabase, updated_row)
        result = notification_service.send(notification)

    assert result["status"] == "failed"
    assert result["error"] == "Network is unreachable"  # surfaced to the admin, not just logged
    mock_supabase.table.return_value.insert.assert_not_called()


def test_send_retries_from_failed_and_can_succeed():
    notification = {"id": "notif-3", "status": "failed", "channel": "email"}
    updated_row = {"id": "notif-3", "status": "sent", "channel": "email"}
    with (
        patch.object(notification_service, "supabase") as mock_supabase,
        patch.object(
            notification_service, "_dispatch",
            return_value=("email", DeliveryResult(success=True, provider_message_id="msg-2")),
        ),
    ):
        _mock_update_and_refetch(mock_supabase, updated_row)
        result = notification_service.send(notification)

    assert result["status"] == "sent"
    # Retrying re-attempts delivery on the SAME row -- never a new one.
    mock_supabase.table.return_value.insert.assert_not_called()


def test_send_success_does_not_carry_a_stale_error_field():
    notification = {"id": "notif-5", "status": "failed", "channel": "email"}
    updated_row = {"id": "notif-5", "status": "sent", "channel": "email"}
    with (
        patch.object(notification_service, "supabase") as mock_supabase,
        patch.object(
            notification_service, "_dispatch",
            return_value=("email", DeliveryResult(success=True, provider_message_id="msg-3")),
        ),
    ):
        _mock_update_and_refetch(mock_supabase, updated_row)
        result = notification_service.send(notification)

    assert "error" not in result


# --- Communications Workspace (Step 2): channel default + list filters ----


def _mock_no_existing_event_notification(mock_supabase) -> None:
    """Configures the idempotency-check chain
    (select().eq().eq().limit().execute()) to report "nothing found yet" --
    the setup every test exercising the create-a-new-notification path
    needs, now that create_notification_for_order_event() checks first.
    """
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )


def test_create_notification_for_order_event_defaults_channel_to_email():
    # The automated, order-status-triggered path must know its intended
    # channel from creation, same as the AI Agent's draft path already
    # does -- not only once _dispatch() resolves one at send time.
    with patch.object(notification_service, "supabase") as mock_supabase:
        _mock_no_existing_event_notification(mock_supabase)
        mock_supabase.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "notif-1", "status": "queued", "channel": "email"}]
        )
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            SimpleNamespace(
                data=[{"id": "notif-1", "status": "draft", "channel": "email", "subject": "x", "body": "y"}]
            )
        )

        notification_service.create_notification_for_order_event(ORDER, "confirmed")

        inserted_payload = mock_supabase.table.return_value.insert.call_args.args[0]
        assert inserted_payload["channel"] == "email"


def test_create_notification_for_order_event_is_idempotent():
    # Step 5's critical requirement: re-processing the same (order, event)
    # -- a re-saved status, a retried request -- must not create a second
    # notification. The existence check finds the one from "before".
    already_existing = {"id": "notif-existing", "status": "draft", "event": "order_confirmed"}
    with patch.object(notification_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
            data=[already_existing]
        )

        result = notification_service.create_notification_for_order_event(ORDER, "confirmed")

        assert result == already_existing
        mock_supabase.table.return_value.insert.assert_not_called()


def test_create_notification_for_order_event_pending_status_creates_order_received():
    with patch.object(notification_service, "supabase") as mock_supabase:
        _mock_no_existing_event_notification(mock_supabase)
        mock_supabase.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "notif-2", "status": "queued", "channel": "email"}]
        )
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "notif-2", "status": "draft", "channel": "email", "subject": "x", "body": "y"}]
        )

        result = notification_service.create_notification_for_order_event(ORDER, "pending")

        assert result is not None
        inserted_payload = mock_supabase.table.return_value.insert.call_args.args[0]
        assert inserted_payload["event"] == "order_received"
        assert inserted_payload["order_id"] == ORDER["id"]


def test_create_notification_for_order_event_never_raises_even_if_the_existence_check_fails():
    # The "never raises" contract must hold for the new idempotency check
    # too, not just for the insert/render steps it already covered.
    with patch.object(notification_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value.select.side_effect = RuntimeError("Supabase is down")
        result = notification_service.create_notification_for_order_event(ORDER, "confirmed")
    assert result is None


def test_create_notification_for_order_event_cancelled_still_lands_at_draft_not_sent():
    # Sensitive case: cancellation must not bypass human review -- the
    # notification lands at the exact same "draft" status every other
    # event does, with no special-cased auto-send/auto-approve path.
    with patch.object(notification_service, "supabase") as mock_supabase:
        _mock_no_existing_event_notification(mock_supabase)
        mock_supabase.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "notif-3", "status": "queued", "channel": "email"}]
        )
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": "notif-3", "status": "draft", "channel": "email", "subject": "x", "body": "y"}]
        )

        result = notification_service.create_notification_for_order_event(ORDER, "cancelled")

        assert result["status"] == "draft"
        update_payload = mock_supabase.table.return_value.update.call_args.args[0]
        assert update_payload["status"] == "draft"  # never anything past draft from this path


def _self_chaining_query_mock(execute_result):
    """A Supabase query-builder mock where every chainable method
    (select/eq/in_/neq/order/range) returns the SAME mock object, so a
    test can assert e.g. `query.eq.assert_any_call(...)` regardless of
    how deep in the real chain that call happens -- not coupled to
    list_notifications()'s exact filter-application order.
    """
    query = MagicMock()
    for method in ("select", "eq", "in_", "neq", "order", "range"):
        getattr(query, method).return_value = query
    query.execute.return_value = execute_result
    return query


def test_list_notifications_filters_by_channel():
    query = _self_chaining_query_mock(SimpleNamespace(data=[], count=0))
    with patch.object(notification_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        notification_service.list_notifications(channel="whatsapp")
    query.eq.assert_any_call("channel", "whatsapp")


def test_list_notifications_source_ai_drafted_filters_by_agent_drafted_event():
    query = _self_chaining_query_mock(SimpleNamespace(data=[], count=0))
    with patch.object(notification_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        notification_service.list_notifications(source="ai_drafted")
    query.eq.assert_any_call("event", "agent_drafted")


def test_list_notifications_source_automated_excludes_agent_drafted_event():
    query = _self_chaining_query_mock(SimpleNamespace(data=[], count=0))
    with patch.object(notification_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        notification_service.list_notifications(source="automated")
    query.neq.assert_any_call("event", "agent_drafted")


def test_list_notifications_statuses_param_uses_in_query_for_needs_review_view():
    query = _self_chaining_query_mock(SimpleNamespace(data=[], count=0))
    with patch.object(notification_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        notification_service.list_notifications(statuses=notification_service.NEEDS_REVIEW_STATUSES)
    query.in_.assert_any_call("status", list(notification_service.NEEDS_REVIEW_STATUSES))


def test_list_notifications_statuses_takes_priority_over_single_status():
    # If a caller somehow passed both (no real caller does), the coarse
    # `view` grouping wins -- documented behavior, not just an accident of
    # if/elif order.
    query = _self_chaining_query_mock(SimpleNamespace(data=[], count=0))
    with patch.object(notification_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value = query
        notification_service.list_notifications(status="queued", statuses=("sent",))
    query.in_.assert_any_call("status", ["sent"])
    query.eq.assert_not_called()


# --- create_staff_message() (Communications Workspace WhatsApp reply) ------


def test_create_staff_message_rejects_invalid_channel():
    _expect_value_error(lambda: notification_service.create_staff_message("cust-1", "sms", "hi"))


def test_create_staff_message_inserts_a_draft_and_returns_it():
    inserted_row = {"id": "notif-1", "customer_id": "cust-1", "channel": "whatsapp", "status": "draft", "body": "hi there"}

    insert_query = MagicMock()
    insert_query.insert.return_value = insert_query
    insert_query.execute.return_value = SimpleNamespace(data=[inserted_row])

    select_query = MagicMock()
    select_query.select.return_value = select_query
    select_query.eq.return_value = select_query
    select_query.maybe_single.return_value = select_query
    select_query.execute.return_value = SimpleNamespace(data=inserted_row)

    with patch.object(notification_service, "supabase") as mock_supabase:
        mock_supabase.table.side_effect = [insert_query, select_query]
        result = notification_service.create_staff_message("cust-1", "whatsapp", "hi there")

    assert result == inserted_row
    insert_payload = insert_query.insert.call_args.args[0]
    assert insert_payload == {
        "customer_id": "cust-1",
        "order_id": None,
        "event": "staff_composed",
        "status": "draft",
        "channel": "whatsapp",
        "subject": None,
        "body": "hi there",
    }


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
