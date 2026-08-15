"""Request/response schemas for the AI Bakery Manager
(`app/api/routes/admin/bakery_manager.py`) — an optional, additive
orchestration layer over the existing deterministic services, NOT a
second admin surface. See `app/services/bakery_manager_service.py`'s
own module docstring for the full architecture.

No new database table backs this: a Plan is generated, returned to the
frontend, and round-tripped for Execute — bakery_manager_service
independently re-validates everything on Execute, so the round-tripped
plan is treated as untrusted input, same as any other client-supplied
data (see that module's own note on why this is safe).
"""

from pydantic import BaseModel


class ProposedAction(BaseModel):
    actionId: str
    actionType: str
    orderId: str | None = None
    customerId: str | None = None
    currentState: str | None = None
    proposedState: str | None = None
    reason: str
    evidence: list[str] = []
    confidence: int
    # Both computed by the application (bakery_manager_service's own
    # allowlist + revalidation), never trusted from Claude's own output —
    # see that module's docstring on why this is the one field Claude's
    # opinion can never set.
    safeToExecute: bool
    requiresManagerAttention: bool
    # Pickup Date + Order Priority, Phase 2: the same CRITICAL/HIGH/NORMAL/
    # LOW label app/services/priority_service.py computes for Back Office
    # display — attached here purely for the manager's benefit (also
    # already present as a line in `evidence`), never read back as an
    # authorization signal.
    priority: str | None = None


class PlanRecommendations(BaseModel):
    staffing: list[str] = []
    inventory: list[str] = []
    workload: list[str] = []
    production: list[str] = []


class PlanException(BaseModel):
    type: str
    detail: str
    orderId: str | None = None
    customerId: str | None = None


class BakeryManagerPlan(BaseModel):
    runId: str
    timestamp: str
    mode: str  # "preview" (Execute never returns this shape -- see ExecutePlanResponse)
    operationalSummary: str
    proposedActions: list[ProposedAction]
    recommendations: PlanRecommendations
    exceptions: list[PlanException]


class ExecuteActionRequest(BaseModel):
    """One action the manager selected via checkbox. Deliberately a small,
    closed shape (not "resubmit the whole ProposedAction") -- the backend
    re-fetches and re-validates everything about the order/customer fresh
    from the database; nothing here beyond actionId/actionType/the target
    reference is actually trusted.
    """

    actionId: str
    actionType: str
    orderId: str | None = None
    customerId: str | None = None
    proposedState: str | None = None


class ExecutePlanRequest(BaseModel):
    runId: str
    actions: list[ExecuteActionRequest]


class ExecutedActionResult(BaseModel):
    actionId: str
    actionType: str
    success: bool
    detail: str
    orderId: str | None = None
    notificationId: str | None = None


class ExecutePlanResponse(BaseModel):
    runId: str
    results: list[ExecutedActionResult]
