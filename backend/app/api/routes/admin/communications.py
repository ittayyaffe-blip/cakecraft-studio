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
from app.schemas.admin_communications import AdminInboxResponse, CheckEmailResponse
from app.services import inbound_service
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
