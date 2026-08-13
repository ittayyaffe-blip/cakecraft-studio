"""Admin notification routes — Event-Driven Customer Communication Platform.

The channel-agnostic notification queue + human approval workflow. Every
route depends on `get_current_admin` (Phase 1's reusable dependency); the
approval step additionally requires the `admin` role specifically
(`require_role("admin")`) — the first route in this project to actually
use that dependency for something beyond its own unit test (see
`docs/PHASE1_IDENTITY_SECURITY.md`, which noted none existed yet). Every
other action here (submit, return-to-draft, send, edit) is open to any
active staff member, matching the Bakery Command Center Blueprint's role
table for Communications ("staff — send only").

Notifications are never created here — `app/api/routes/admin/orders.py`'s
status-update route creates them (see notification_service.create_notification_for_order_event).
This module only ever moves an *existing* notification through its
lifecycle, and logs each transition to the audit log the same way
admin/orders.py's status-update route already does for orders.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_admin, require_role
from app.schemas.admin_communications import AdminInboundMessage
from app.schemas.admin_notification import (
    AdminNotification,
    AdminNotificationListResponse,
    NotificationContentUpdateRequest,
)
from app.services import inbound_service, notification_service
from app.services.audit_service import record_event
from app.services.auth_service import AdminIdentity
from app.services.notification_service import (
    NEEDS_REVIEW_STATUSES,
    NOTIFICATION_STATUSES,
    VALID_CHANNELS,
    VALID_SOURCES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/notifications", tags=["admin-notifications"])

# Communications Workspace (Step 2) primary views — a coarse, human-facing
# grouping over the underlying `status` values, resolved to the `statuses`
# param list_notifications() actually filters on. `None` means "no status
# filter" (All). Kept here, not in notification_service.py, since "view" is
# this route's own API-facing vocabulary, not core domain vocabulary other
# callers need — NEEDS_REVIEW_STATUSES itself (the real domain knowledge)
# still lives in notification_service.py.
VIEW_STATUSES: dict[str, tuple[str, ...] | None] = {
    "needs_review": NEEDS_REVIEW_STATUSES,
    "sent": ("sent",),
    "all": None,
}


def _require_existing_notification(notification_id: str) -> dict:
    """Shared existence check for every /{notification_id}/... route
    below — the same defensive, independently-correct pattern
    admin/customers.py's sub-resource routes already use.
    """
    try:
        notification = notification_service.get_notification_by_id(notification_id)
    except Exception:
        logger.exception("Failed to fetch notification")
        raise HTTPException(status_code=500, detail="Failed to fetch notification")

    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification


def _apply_transition(notification: dict, admin: AdminIdentity, transition_fn, action_name: str) -> dict:
    """Run one lifecycle transition, map its ValueError (invalid current
    status) to 400, and log the resulting change to the audit log — shared
    by every action route below so the try/except/audit-log sequence isn't
    repeated four times.
    """
    try:
        updated = transition_fn(notification)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Failed to transition notification %s", notification["id"])
        raise HTTPException(status_code=500, detail="Failed to update notification")

    record_event(
        actor_id=admin.id,
        action=action_name,
        entity_type="notifications",
        entity_id=notification["id"],
        before={"status": notification["status"]},
        after={"status": updated["status"]},
    )
    return updated


@router.get("", response_model=AdminNotificationListResponse)
def list_notifications(
    status: str | None = None,
    view: str | None = None,
    channel: str | None = None,
    source: str | None = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    admin: AdminIdentity = Depends(get_current_admin),
):
    # `status` (exact match, e.g. "queued") is the original Sprint 1
    # filter — still valid, unused by the Communications Workspace UI now
    # but not removed, matching this route's own established idiom
    # (orders.py's list_orders validates its own filter value the same
    # way). `view` is the new coarse grouping the UI actually drives.
    if status is not None and status not in NOTIFICATION_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    if view is not None and view not in VIEW_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid view: {view}")
    if channel is not None and channel not in VALID_CHANNELS:
        raise HTTPException(status_code=400, detail=f"Invalid channel: {channel}")
    if source is not None and source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail=f"Invalid source: {source}")

    try:
        return notification_service.list_notifications(
            status=status,
            statuses=VIEW_STATUSES.get(view) if view else None,
            channel=channel,
            source=source,
            page=page,
            page_size=pageSize,
        )
    except Exception:
        logger.exception("Failed to list notifications")
        raise HTTPException(status_code=500, detail="Failed to list notifications")


@router.get("/{notification_id}", response_model=AdminNotification)
def get_notification(notification_id: uuid.UUID, admin: AdminIdentity = Depends(get_current_admin)):
    return _require_existing_notification(str(notification_id))


@router.get("/{notification_id}/source-message", response_model=AdminInboundMessage | None)
def get_source_message(notification_id: uuid.UUID, admin: AdminIdentity = Depends(get_current_admin)):
    """The inbound customer message this draft was created from, if any
    (Step 3) — null for every notification created by the *other* paths
    (an order-status change, or a staff-initiated on-demand draft), not
    an error. The Communications drawer calls this alongside the regular
    GET above to decide whether to render the "Customer message" section.
    Doesn't require the notification to exist first: no source message
    for an unknown id is exactly as valid a "null" as no source message
    for a real one.
    """
    try:
        return inbound_service.get_source_message_for_notification(str(notification_id))
    except Exception:
        logger.exception("Failed to fetch source message for notification %s", notification_id)
        raise HTTPException(status_code=500, detail="Failed to fetch the source message")


@router.patch("/{notification_id}", response_model=AdminNotification)
def edit_notification(
    notification_id: uuid.UUID,
    body: NotificationContentUpdateRequest,
    admin: AdminIdentity = Depends(get_current_admin),
):
    notification = _require_existing_notification(str(notification_id))

    try:
        updated = notification_service.update_draft_content(notification, body.subject, body.body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Failed to edit notification %s", notification_id)
        raise HTTPException(status_code=500, detail="Failed to edit notification")

    record_event(
        actor_id=admin.id,
        action="notification.edited",
        entity_type="notifications",
        entity_id=str(notification_id),
        before={"subject": notification["subject"], "body": notification["body"]},
        after={"subject": body.subject, "body": body.body},
    )
    return updated


@router.post("/{notification_id}/submit", response_model=AdminNotification)
def submit_notification(notification_id: uuid.UUID, admin: AdminIdentity = Depends(get_current_admin)):
    notification = _require_existing_notification(str(notification_id))
    return _apply_transition(
        notification, admin, notification_service.submit_for_approval, "notification.submitted"
    )


@router.post("/{notification_id}/approve", response_model=AdminNotification)
def approve_notification(
    notification_id: uuid.UUID, admin: AdminIdentity = Depends(require_role("admin"))
):
    notification = _require_existing_notification(str(notification_id))
    return _apply_transition(notification, admin, notification_service.approve, "notification.approved")


@router.post("/{notification_id}/return-to-draft", response_model=AdminNotification)
def return_notification_to_draft(
    notification_id: uuid.UUID, admin: AdminIdentity = Depends(get_current_admin)
):
    notification = _require_existing_notification(str(notification_id))
    return _apply_transition(
        notification, admin, notification_service.return_to_draft, "notification.returned_to_draft"
    )


@router.post("/{notification_id}/send", response_model=AdminNotification)
def send_notification(notification_id: uuid.UUID, admin: AdminIdentity = Depends(get_current_admin)):
    """Unlike every other action in this file, this one has two possible
    real outcomes as of Sprint 3 (Communication Adapter + Gmail) — a
    configured adapter's delivery attempt can genuinely fail, landing the
    notification on "failed" instead of "sent" (see
    notification_service.send()). `_apply_transition` above assumes one
    fixed action name per route, which no longer fits here, so this route
    picks the audit action name from the real outcome instead of reusing
    that shared helper — the other three transition routes (submit,
    approve, return-to-draft) still only ever have one outcome each, so
    they're unaffected.
    """
    notification = _require_existing_notification(str(notification_id))

    try:
        updated = notification_service.send(notification)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Failed to send notification %s", notification_id)
        raise HTTPException(status_code=500, detail="Failed to send notification")

    action = "notification.sent" if updated["status"] == "sent" else "notification.send_failed"
    record_event(
        actor_id=admin.id,
        action=action,
        entity_type="notifications",
        entity_id=str(notification_id),
        before={"status": notification["status"]},
        after={"status": updated["status"]},
    )
    return updated
