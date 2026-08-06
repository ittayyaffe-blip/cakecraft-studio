"""AI Operations Agent routes — Business Intelligence Layer. See
docs/BUSINESS_INTELLIGENCE_LAYER.md "AI Agent Design".

Three endpoints, same auth pattern as every other admin route:
  - GET  /admin/agent/morning-briefing — synthesized operational narrative
  - POST /admin/agent/ask              — "what should I prepare tomorrow?"
  - POST /admin/agent/draft-communication — drafts a notification (draft
    status only — see agent_service.draft_customer_communication's own
    docstring on why this never sends anything itself)

The first two are read-only, like dashboard.py/briefing.py, so nothing
there touches the audit log. draft-communication *creates* a row, so it
logs to the audit log the same way every other notification-creating
action in this project does — the one difference from a normal
staff-authored draft is `actor_id=None` (system/AI-generated, the same
convention the demo data seeder's system-generated audit events already
use), so the audit trail honestly reflects that a human didn't write it,
even though a human (the admin calling this endpoint) requested it.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_admin
from app.schemas.admin_agent import (
    AgentAskRequest,
    AgentAskResponse,
    DraftCommunicationRequest,
    DraftCommunicationResponse,
    MorningBriefingResponse,
)
from app.services import agent_service
from app.services.audit_service import record_event
from app.services.auth_service import AdminIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/agent", tags=["admin-agent"])


@router.get("/morning-briefing", response_model=MorningBriefingResponse)
def morning_briefing(admin: AdminIdentity = Depends(get_current_admin)):
    try:
        return agent_service.generate_morning_briefing()
    except Exception:
        logger.exception("Morning briefing generation failed")
        raise HTTPException(status_code=500, detail="Failed to generate the morning briefing")


@router.post("/ask", response_model=AgentAskResponse)
def ask(request: AgentAskRequest, admin: AdminIdentity = Depends(get_current_admin)):
    try:
        return agent_service.ask_operations_question(request.question)
    except Exception:
        logger.exception("Agent ask failed for question: %s", request.question)
        raise HTTPException(status_code=500, detail="Failed to answer the question")


@router.post("/draft-communication", response_model=DraftCommunicationResponse)
def draft_communication(request: DraftCommunicationRequest, admin: AdminIdentity = Depends(get_current_admin)):
    try:
        draft = agent_service.draft_customer_communication(request.orderId, request.instruction)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Draft communication generation failed for order %s", request.orderId)
        raise HTTPException(status_code=500, detail="Failed to draft the communication")

    record_event(
        actor_id=None,  # AI-generated, not staff-authored — see module docstring
        action="notification.ai_drafted",
        entity_type="notifications",
        entity_id=draft["id"],
        before=None,
        after={"status": draft["status"], "requestedBy": admin.id, "instruction": request.instruction},
    )
    return draft
