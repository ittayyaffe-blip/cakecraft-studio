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

from app.services import notification_service, notification_templates

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
    assert notification_templates.get_template_for_status("pending") is None


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
    _expect_value_error(
        lambda: notification_service.send({"status": "awaiting_approval", "id": "x"})
    )


def test_update_draft_content_rejects_non_draft():
    _expect_value_error(
        lambda: notification_service.update_draft_content(
            {"status": "approved", "id": "x", "subject": "old", "body": "old"}, "new", "new"
        )
    )


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
