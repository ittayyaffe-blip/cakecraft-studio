"""Request/response schemas for the AI Operations Agent endpoints
(`app/api/routes/admin/agent.py`) — Business Intelligence Layer.

DraftCommunicationResponse reuses `admin_notification.py`'s
`AdminNotification` directly: `agent_service.draft_customer_communication`
inserts into the same `notifications` table, in the same shape, as
every other notification — no reason to model it twice.
"""

from pydantic import BaseModel

from app.schemas.admin_notification import AdminNotification


class AgentSource(BaseModel):
    title: str
    sourceFile: str


class AgentAskRequest(BaseModel):
    question: str


class AgentAskResponse(BaseModel):
    answer: str
    sources: list[AgentSource]


class MorningBriefingResponse(BaseModel):
    narrative: str
    productionNotes: str | None = None
    staffingNotes: str | None = None
    inventoryNotes: str | None = None
    sources: list[AgentSource]


class DraftCommunicationRequest(BaseModel):
    orderId: str
    instruction: str | None = None


class DraftCommunicationResponse(AdminNotification):
    pass
