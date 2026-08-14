"""Admin inbound-communication routes — Step 3.

Two small, human-triggered actions layered on top of inbound_service.py:
checking for new email on demand (the same pipeline main.py's background
poll loop also runs on a timer — see that module), and listing the
"Inbox" — inbound messages that don't yet have a resulting draft (unknown
sender, AI failure, or still pending), so nothing a customer wrote is
ever silently lost even when the AI Agent couldn't turn it into a draft.

Same auth pattern as every other admin route: `get_current_admin` only —
open to any active staff member, matching the rest of the Communications
workspace (only *approving* a notification is admin-role-gated, and that
restriction lives on notifications.py's existing /approve route,
unchanged by Step 3).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_admin
from app.schemas.admin_communications import (
    AdminInboxResponse,
    CheckEmailResponse,
    WhatsAppReplyRequest,
    WhatsAppStatusResponse,
    WhatsAppThreadResponse,
)
from app.schemas.admin_notification import AdminNotification
from app.services import communication, customer_service, inbound_service, notification_service
from app.services.auth_service import AdminIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/communications", tags=["admin-communications"])


@router.post("/check-email", response_model=CheckEmailResponse)
def check_email(admin: AdminIdentity = Depends(get_current_admin)):
    """Fetch + process any currently-unread inbound email right now,
    rather than waiting for the next background poll tick — mainly for
    the Communications workspace's "Check for new messages" button and
    for testing. Never sends anything: the pipeline this calls only ever
    creates `draft` notifications (see agent_service.
    draft_reply_to_inbound_message), same guarantee as every other AI
    Agent draft path in this project.
    """
    try:
        items = inbound_service.check_for_new_email()
    except Exception:
        logger.exception("Manual check-email trigger failed")
        raise HTTPException(status_code=500, detail="Failed to check for new email")
    return {"checked": len(items), "items": items}


@router.get("/inbox", response_model=AdminInboxResponse)
def inbox(admin: AdminIdentity = Depends(get_current_admin)):
    try:
        return {"items": inbound_service.list_inbox()}
    except Exception:
        logger.exception("Failed to list inbound message inbox")
        raise HTTPException(status_code=500, detail="Failed to load the inbox")


@router.get("/whatsapp-status", response_model=WhatsAppStatusResponse)
def whatsapp_status(admin: AdminIdentity = Depends(get_current_admin)):
    """Which WhatsApp provider (if any) is currently live — the
    Communications Workspace's status indicator. Read-only, never
    triggers a real send or touches Twilio/Meta directly; just reports
    which adapter (if any) the registry currently has for "whatsapp".
    """
    return communication.whatsapp_status()


@router.get("/whatsapp/thread/{customer_id}", response_model=WhatsAppThreadResponse)
def whatsapp_thread(customer_id: str, admin: AdminIdentity = Depends(get_current_admin)):
    """One customer's full WhatsApp conversation, merged and chronological
    — the Communications Workspace's WhatsApp thread view. Not a new
    message store: "incoming" comes from the existing `inbound_messages`
    table (inbound_service.list_channel_messages_for_customer), "outgoing"
    from the existing `notifications` table (notification_service.
    list_notifications_for_customer, filtered to channel="whatsapp" here
    — that function itself stays channel-agnostic, matching every other
    call site). Read-only; sending happens through the existing
    /admin/notifications/{id}/send route, unchanged.
    """
    customer = customer_service.get_customer_by_id(customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    try:
        incoming = inbound_service.list_channel_messages_for_customer(customer_id, "whatsapp")
        outgoing = [
            n for n in notification_service.list_notifications_for_customer(customer_id) if n.get("channel") == "whatsapp"
        ]
    except Exception:
        logger.exception("Failed to load WhatsApp thread for customer %s", customer_id)
        raise HTTPException(status_code=500, detail="Failed to load the WhatsApp thread")

    messages = [
        {"direction": "incoming", "body": m["body"], "subject": None, "timestamp": m["received_at"], "status": None}
        for m in incoming
    ] + [
        {
            "direction": "outgoing",
            "body": n["body"],
            "subject": n.get("subject"),
            "timestamp": n.get("sent_at") or n["created_at"],
            "status": n["status"],
        }
        for n in outgoing
    ]
    messages.sort(key=lambda m: m["timestamp"])

    return {"customer": customer, "messages": messages}


@router.post("/whatsapp/reply", response_model=AdminNotification)
def whatsapp_reply(body: WhatsAppReplyRequest, admin: AdminIdentity = Depends(get_current_admin)):
    """Create a draft WhatsApp notification from staff-typed text — the
    WhatsApp thread view's reply composer. Deliberately creates only:
    sending is the existing, unchanged POST /admin/notifications/{id}/
    send route, called as the composer's own separate second step (same
    two-step shape as every other draft in this project — a message is
    never sent as a side effect of being created).
    """
    if not body.body.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if customer_service.get_customer_by_id(body.customerId) is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    try:
        return notification_service.create_staff_message(body.customerId, "whatsapp", body.body.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Failed to create staff WhatsApp reply for customer %s", body.customerId)
        raise HTTPException(status_code=500, detail="Failed to create the reply")
