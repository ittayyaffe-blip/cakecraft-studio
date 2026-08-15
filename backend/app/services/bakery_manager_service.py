"""AI Bakery Manager — an optional, additive orchestration layer over the
same deterministic services the human Back Office manager already uses.
See docs/FINAL_ARCHITECTURE.md's "AI Bakery Manager" section for the
full architecture write-up; in one paragraph:

    CakeCraft separates deterministic business logic from AI.
    Authentication, authorization, pricing, payment, order-state
    transitions, and safety validation are controlled by application
    logic. AI is used for assistance, forecasting interpretation,
    grounded knowledge, and communication drafting — not as the
    authority over critical business operations. The AI Manager has
    autonomy only within explicitly defined operational boundaries: it
    may propose actions, but deterministic CakeCraft services remain
    the authority over whether an action is allowed and how it is
    executed.

This is a THIN module, deliberately: it reuses briefing_service (today's
stats + forecast + high-priority orders), forecast_service (via
briefing_service, not re-derived), rag_service (grounding), order_service
(the transition graph — the actual authority), notification_service (draft
creation), audit_service (the one audit log), and agent_service's own
Claude-call plumbing (`_claude`/`_parse_json_response`, reused directly
rather than re-implemented — see get_preview_plan's own note). Nothing
here talks to Supabase for anything order_service/notification_service
already owns; the one place this module reads `orders`/`payments`
directly is the same read-only aggregate pattern dashboard_service.py
and briefing_service.py already use for their own multi-order views.

Two entry points, matching the two-mode design:
  - get_preview_plan() — fully read-only. Gathers live data
    deterministically, makes exactly ONE Claude call to turn it into a
    structured plan, then independently re-classifies every proposed
    action against the real transition graph and a deterministic
    production-timing rule — Claude's own "this seems safe" opinion is
    never trusted, only ever downgraded. Nothing is written.
  - execute_plan() — the manager's approved, checkbox-selected actions
    only. Re-validates every single one from scratch against the live
    database (the round-tripped plan from the frontend is untrusted
    input, exactly like any other client-supplied data) before calling
    the one real service function a human action would call. Zero
    Claude calls. Any action outside the closed executable allowlist is
    rejected outright, never attempted.
"""

import logging
import uuid
from datetime import datetime, timezone

from app.services import agent_service, briefing_service, notification_service, order_service, rag_service
from app.services.audit_service import record_event

logger = logging.getLogger(__name__)

# --- The closed allowlist -----------------------------------------------
# The ONLY action types execute_plan() will ever call a real service for.
# Everything else Claude might propose (advance_to_ready,
# advance_to_completed, reprioritize_production, staffing_adjustment, a
# typo'd variant, anything never-autonomous per the architecture report)
# is still shown to the manager as a recommendation -- see
# _classify_action -- but can never reach execution, structurally: a
# string not in this set simply has no branch in _execute_one below.
_EXECUTABLE_ACTION_TYPES = frozenset({
    "advance_to_in_progress",
    "create_customer_update_draft",
    "create_staff_note_draft",
})

# Recommendation-only types the planning prompt is allowed to use --
# listed explicitly (rather than "anything else") so the prompt gives
# Claude a real, closed vocabulary instead of inventing arbitrary
# strings; still always safeToExecute=False regardless, same as a
# genuinely unrecognized type (see _classify_action).
_RECOMMENDATION_ONLY_ACTION_TYPES = frozenset({
    "advance_to_ready",
    "advance_to_completed",
    "reprioritize_production",
    "staffing_adjustment",
    "inventory_check",
    "rush_order_attention",
})

_ALL_KNOWN_ACTION_TYPES = _EXECUTABLE_ACTION_TYPES | _RECOMMENDATION_ONLY_ACTION_TYPES

# Deterministic production-start rule (Section 7 of the architecture
# report): reuses the EXACT "due within 2 days" urgency threshold
# briefing_service._high_priority_orders() already applies for
# "pickup due today or overdue" / "pickup due soon" -- not a new number
# invented for this feature. production_workflow.md's own "schedule
# backward from pickup, don't start too late" principle means a
# confirmed order this close to its pickup date, with production not
# yet started, is unambiguously due to start now, not a judgment call.
# ponytail: a fixed day-count, not a per-category production-duration
# model (Wedding/Corporate/Birthday all get the same 2-day window) --
# upgrade path is a real per-category duration config if this ever
# needs to be more precise than "reuse the existing urgency signal".
_PRODUCTION_START_WITHIN_DAYS = 2


def _production_start_eligibility(order: dict) -> tuple[bool, list[str]]:
    """Deterministic, Python-only -- computed BEFORE Claude ever sees this
    order, and re-computed again, fresh, during execute_plan(). Returns
    (eligible, evidence_lines). Never invents a pickup date: a missing
    one is always ineligible, with its own explicit evidence line (see
    get_preview_plan's exceptions handling, which also surfaces this as
    a real exception, not just a quietly-unchecked box).
    """
    pickup_date = order.get("pickup_date")
    if not pickup_date:
        return False, ["No pickup date on record -- production start timing cannot be safely automated."]

    try:
        days_out = (datetime.fromisoformat(pickup_date).date() - datetime.now(timezone.utc).date()).days
    except ValueError:
        return False, [f"pickup_date '{pickup_date}' could not be parsed."]

    if days_out <= _PRODUCTION_START_WITHIN_DAYS:
        return True, [f"Pickup date {pickup_date} is {days_out} day(s) out (within the {_PRODUCTION_START_WITHIN_DAYS}-day production-start window)."]
    return False, [f"Pickup date {pickup_date} is {days_out} days out -- not yet within the {_PRODUCTION_START_WITHIN_DAYS}-day production-start window."]


def _gather_context() -> dict:
    """Everything the planning prompt needs, gathered deterministically
    and sequentially -- this codebase has no existing concurrency
    pattern in its service layer (every Supabase call anywhere else is
    synchronous, one at a time), and a manager-triggered, few-times-a-day
    Back Office action has no real latency pressure, so introducing one
    here (asyncio.gather/threading) would be new complexity this feature
    doesn't need. See docs/FINAL_ARCHITECTURE.md's own "few seconds is
    acceptable" framing.
    """
    briefing = briefing_service.get_daily_briefing()

    confirmed_orders = order_service.list_orders(status="confirmed", page_size=100)["items"]
    in_progress_orders = order_service.list_orders(status="in_progress", page_size=100)["items"]
    ready_orders = order_service.list_orders(status="ready", page_size=100)["items"]

    confirmed_with_eligibility = []
    for order in confirmed_orders:
        eligible, evidence = _production_start_eligibility(order)
        confirmed_with_eligibility.append({**order, "_productionStartEligible": eligible, "_evidence": evidence})

    knowledge = rag_service.retrieve("production scheduling, lead times, and priority order within a day", top_k=3)

    return {
        "briefing": briefing,
        "confirmed_orders": confirmed_with_eligibility,
        "in_progress_orders": in_progress_orders,
        "ready_orders": ready_orders,
        "knowledge": knowledge,
    }


def _order_summary_line(order: dict) -> str:
    template = order.get("cake_templates") or {}
    customer = order.get("customers") or {}
    return (
        f"- id={order['id']} customer={customer.get('name', '?')} "
        f"cake={template.get('name', '?')} ({template.get('category', '?')}) "
        f"pickup_date={order.get('pickup_date') or 'NOT SET'}"
    )


def _build_planning_prompt(context: dict) -> str:
    briefing = context["briefing"]
    confirmed_lines = "\n".join(
        f"{_order_summary_line(o)} production_start_eligible={o['_productionStartEligible']} ({'; '.join(o['_evidence'])})"
        for o in context["confirmed_orders"]
    ) or "(none)"
    in_progress_lines = "\n".join(_order_summary_line(o) for o in context["in_progress_orders"]) or "(none)"
    ready_lines = "\n".join(_order_summary_line(o) for o in context["ready_orders"]) or "(none)"
    knowledge_context = "\n\n".join(f"[{c['title']}]\n{c['content']}" for c in context["knowledge"])

    return f"""You are the AI Bakery Manager for Maison de Gâteau Paris, a bakery. You PROPOSE a structured
operations plan for the human manager to review — you never act directly, and your own judgment of
whether something is safe to execute is advisory only; the application independently decides that.

ALLOWED actionType values — use ONLY these, never invent a new one:
- "advance_to_in_progress" (order confirmed -> in_progress)
- "advance_to_ready" (recommend only — a baker must physically confirm decoration is complete)
- "advance_to_completed" (recommend only — requires actual customer pickup)
- "create_customer_update_draft" (order_id required)
- "create_staff_note_draft" (customer_id required, write a short body/reason for the note)
- "reprioritize_production", "staffing_adjustment", "inventory_check", "rush_order_attention" (recommend only)

CRITICAL RULES:
- "advance_to_in_progress" may only be proposed for an order where production_start_eligible=true above
  (already computed deterministically — do not propose it for any order marked false, and do not propose
  it for an order missing a pickup date; note that as an exception instead, do not guess a date).
- Never propose payment, refund, price, cancellation, catalog, customer-data, allergy, or send/Email/WhatsApp
  actions — these are not in the allowed actionType list and are outside your role entirely.
- confidence is 0-100, your own honest estimate — it does not determine whether anything executes.

LIVE OPERATIONAL DATA:
- Today: {briefing['todaysOrders']} orders, ${briefing['todaysRevenue']:.2f} revenue
- Tomorrow's forecast: {briefing['forecast']['predictedOrders']} orders, ${briefing['forecast']['predictedRevenue']:.2f} revenue, {briefing['forecast']['workloadLevel']} workload, {briefing['forecast']['confidence']}% confidence. Reason: {briefing['forecast']['reason']}
- High priority orders: {briefing['highPriorityOrders']}

CONFIRMED ORDERS (candidates for advance_to_in_progress):
{confirmed_lines}

IN_PROGRESS ORDERS (candidates for advance_to_ready — recommend only):
{in_progress_lines}

READY ORDERS (candidates for advance_to_completed — recommend only):
{ready_lines}

RELEVANT BAKERY OPERATING POLICY:
{knowledge_context}

Respond with ONLY this JSON object, nothing else:
{{"operationalSummary": "2-3 sentences, concrete, in the style of a knowledgeable colleague",
"proposedActions": [{{"actionType": "...", "orderId": "..." or null, "customerId": "..." or null,
"currentState": "..." or null, "proposedState": "..." or null, "reason": "...", "evidence": ["..."],
"confidence": 0-100}}],
"recommendations": {{"staffing": ["..."], "inventory": ["..."], "workload": ["..."], "production": ["..."]}},
"exceptions": [{{"type": "...", "detail": "...", "orderId": "..." or null, "customerId": "..." or null}}]}}"""


def _revalidate_order_for_action(action_type: str, order_id: str | None) -> tuple[bool, list[str], dict | None]:
    """The one real authority check, called identically by _classify_action
    (Preview) and execute_plan (Execute) — re-fetches the order fresh from
    the database every time (never trusts a round-tripped copy) and checks
    it against order_service's own transition graph plus the deterministic
    production-timing rule. Returns (safe, evidence, order-or-None).
    """
    if action_type != "advance_to_in_progress":
        return False, [], None

    if not order_id:
        return False, ["No order id provided."], None

    order = order_service.get_order_by_id(order_id)
    if order is None:
        return False, ["Order no longer exists."], None

    if order["status"] != "confirmed":
        return False, [f"Order is now '{order['status']}', not 'confirmed' — state changed since this was proposed."], order

    if "in_progress" not in order_service._ALLOWED_STATUS_TRANSITIONS.get(order["status"], set()):
        return False, [f"'{order['status']}' -> 'in_progress' is not an allowed transition."], order

    eligible, evidence = _production_start_eligibility(order)
    return eligible, evidence, order


def _classify_action(raw: dict) -> dict:
    """Turns one of Claude's raw proposed-action dicts into the real
    ProposedAction shape — safeToExecute and requiresManagerAttention are
    ALWAYS computed here, by the application, never read from anything
    Claude wrote (Claude's JSON is never asked for these two fields at
    all, structurally, not just by convention — see _build_planning_prompt).
    """
    action_type = raw.get("actionType") if isinstance(raw.get("actionType"), str) else None
    order_id = raw.get("orderId") if isinstance(raw.get("orderId"), str) else None
    customer_id = raw.get("customerId") if isinstance(raw.get("customerId"), str) else None
    evidence = list(raw.get("evidence") or [])

    if action_type not in _ALL_KNOWN_ACTION_TYPES:
        safe = False
        requires_attention = True
        evidence.append(f"Unrecognized action type '{action_type}' — not in the allowed list.")
    elif action_type not in _EXECUTABLE_ACTION_TYPES:
        # A real, known recommendation-only type (advance_to_ready, etc.)
        # -- always shown, never executable, per the architecture report.
        safe = False
        requires_attention = False
    elif action_type == "advance_to_in_progress":
        safe, extra_evidence, _order = _revalidate_order_for_action(action_type, order_id)
        evidence.extend(extra_evidence)
        requires_attention = not safe
    else:
        # create_customer_update_draft / create_staff_note_draft: low-risk,
        # idempotent, never-sent draft creation -- safe whenever the
        # referenced order/customer genuinely exists.
        exists = bool(order_id and order_service.get_order_by_id(order_id)) or bool(customer_id)
        safe = exists
        requires_attention = not exists
        if not exists:
            evidence.append("Referenced order/customer could not be found.")

    return {
        "actionId": f"a-{uuid.uuid4().hex[:8]}",
        "actionType": action_type or "unknown",
        "orderId": order_id,
        "customerId": customer_id,
        "currentState": raw.get("currentState") if isinstance(raw.get("currentState"), str) else None,
        "proposedState": raw.get("proposedState") if isinstance(raw.get("proposedState"), str) else None,
        "reason": (raw.get("reason") or "").strip() or "No reason provided.",
        "evidence": evidence,
        "confidence": raw.get("confidence") if isinstance(raw.get("confidence"), int) else 0,
        "safeToExecute": safe,
        "requiresManagerAttention": requires_attention,
    }


def _missing_pickup_date_exceptions(confirmed_orders: list[dict]) -> list[dict]:
    """Deterministically, not left to Claude's own attention -- every
    confirmed order missing a pickup date gets its own exception, always,
    regardless of whether Claude's plan happened to mention it.
    """
    return [
        {
            "type": "missing_pickup_date",
            "detail": "Pickup date missing — manager attention required.",
            "orderId": order["id"],
            "customerId": order.get("customer_id"),
        }
        for order in confirmed_orders
        if not order.get("pickup_date")
    ]


def get_preview_plan(admin_id: str) -> dict:
    """READ-ONLY. Gathers live operational data deterministically, makes
    exactly ONE Claude call (reusing agent_service._claude/
    _parse_json_response directly rather than re-implementing the same
    client-construction/JSON-parsing logic a second time), then
    independently classifies every proposed action. Never writes to
    orders/notifications; the one write is the audit log entry recording
    that a plan was generated, the same "fail open, never block the
    caller" contract every other audit_service.record_event call site
    already has.
    """
    context = _gather_context()
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    if not agent_service.is_configured():
        plan = {
            "runId": run_id,
            "timestamp": timestamp,
            "mode": "preview",
            "operationalSummary": "AI Bakery Manager couldn't generate a plan right now — the manual Back Office remains fully available.",
            "proposedActions": [],
            "recommendations": {"staffing": [], "inventory": [], "workload": [], "production": []},
            "exceptions": _missing_pickup_date_exceptions(context["confirmed_orders"]),
        }
        record_event(actor_id=admin_id, action="agent.plan_generated", entity_type="bakery_manager_run", entity_id=run_id, after={"proposedActionCount": 0, "reason": "not_configured"})
        return plan

    try:
        raw = agent_service._claude(_build_planning_prompt(context), max_tokens=1500)
        parsed = agent_service._parse_json_response(raw)
    except Exception:
        logger.exception("AI Bakery Manager planning call failed")
        parsed = None

    if parsed is None:
        plan = {
            "runId": run_id,
            "timestamp": timestamp,
            "mode": "preview",
            "operationalSummary": "AI Bakery Manager couldn't generate a plan right now — the manual Back Office remains fully available.",
            "proposedActions": [],
            "recommendations": {"staffing": [], "inventory": [], "workload": [], "production": []},
            "exceptions": _missing_pickup_date_exceptions(context["confirmed_orders"]),
        }
        record_event(actor_id=admin_id, action="agent.plan_generated", entity_type="bakery_manager_run", entity_id=run_id, after={"proposedActionCount": 0, "reason": "ai_call_failed"})
        return plan

    proposed_actions = [_classify_action(a) for a in (parsed.get("proposedActions") or []) if isinstance(a, dict)]

    recommendations = parsed.get("recommendations") or {}
    exceptions = list(parsed.get("exceptions") or [])
    exceptions.extend(_missing_pickup_date_exceptions(context["confirmed_orders"]))
    if context["in_progress_orders"]:
        exceptions.append({
            "type": "manual_confirmation_required",
            "detail": "Physical completion must be confirmed by staff before an order can move to Ready.",
            "orderId": None, "customerId": None,
        })
    if context["ready_orders"]:
        exceptions.append({
            "type": "manual_confirmation_required",
            "detail": "Customer pickup must be confirmed by staff before an order can move to Completed.",
            "orderId": None, "customerId": None,
        })

    plan = {
        "runId": run_id,
        "timestamp": timestamp,
        "mode": "preview",
        "operationalSummary": (parsed.get("operationalSummary") or "").strip() or "No summary available.",
        "proposedActions": proposed_actions,
        "recommendations": {
            "staffing": list(recommendations.get("staffing") or []),
            "inventory": list(recommendations.get("inventory") or []),
            "workload": list(recommendations.get("workload") or []),
            "production": list(recommendations.get("production") or []),
        },
        "exceptions": exceptions,
    }

    record_event(
        actor_id=admin_id, action="agent.plan_generated", entity_type="bakery_manager_run", entity_id=run_id,
        after={"proposedActionCount": len(proposed_actions), "safeToExecuteCount": sum(1 for a in proposed_actions if a["safeToExecute"])},
    )
    return plan


def _execute_one(admin_id: str, run_id: str, action: dict) -> dict:
    """One selected action, fully re-validated against the live database
    before anything is called — the action dict the frontend sent back is
    untrusted input, same posture as any other client-supplied payload
    (see this module's own docstring). Never calls Claude. Never lets a
    failure here raise past this function -- one bad action must not take
    down the rest of the batch (see execute_plan).
    """
    action_id = action.get("actionId", "unknown")
    action_type = action.get("actionType")
    order_id = action.get("orderId")
    customer_id = action.get("customerId")

    def _reject(detail: str) -> dict:
        record_event(
            actor_id=admin_id, action="agent.action_rejected", entity_type="bakery_manager_action",
            entity_id=order_id or customer_id, after={"runId": run_id, "actionId": action_id, "actionType": action_type, "reason": detail},
        )
        return {"actionId": action_id, "actionType": action_type, "success": False, "detail": detail, "orderId": order_id, "notificationId": None}

    if action_type not in _EXECUTABLE_ACTION_TYPES:
        return _reject(f"'{action_type}' is not an executable action type.")

    try:
        if action_type == "advance_to_in_progress":
            safe, evidence, order = _revalidate_order_for_action(action_type, order_id)
            if not safe or order is None:
                return _reject("; ".join(evidence) or "Action is no longer safe to execute.")

            before_status = order["status"]
            updated = order_service.update_order_status(order_id, "in_progress", current_status=before_status)
            notification = notification_service.create_notification_for_order_event(updated, "in_progress")

            record_event(
                actor_id=admin_id, action="agent.action_executed", entity_type="orders", entity_id=order_id,
                before={"status": before_status}, after={"status": "in_progress", "runId": run_id, "actionId": action_id},
            )
            return {
                "actionId": action_id, "actionType": action_type, "success": True,
                "detail": "Order advanced to In Progress.", "orderId": order_id,
                "notificationId": notification["id"] if notification else None,
            }

        if action_type == "create_customer_update_draft":
            order = order_service.get_order_by_id(order_id) if order_id else None
            if order is None:
                return _reject("Order not found.")
            notification = notification_service.create_notification_for_order_event(order, order["status"])
            record_event(
                actor_id=admin_id, action="agent.action_executed", entity_type="notifications",
                entity_id=notification["id"] if notification else None,
                after={"orderId": order_id, "runId": run_id, "actionId": action_id},
            )
            return {
                "actionId": action_id, "actionType": action_type, "success": notification is not None,
                "detail": "Customer-update draft created." if notification else "No draft was needed (already exists, or this status has no customer template).",
                "orderId": order_id, "notificationId": notification["id"] if notification else None,
            }

        if action_type == "create_staff_note_draft":
            if not customer_id:
                return _reject("No customer id provided.")
            body = (action.get("reason") or "AI Bakery Manager flagged this order for a manager note.").strip()
            notification = notification_service.create_staff_message(customer_id, "email", body, order_id=order_id)
            record_event(
                actor_id=admin_id, action="agent.action_executed", entity_type="notifications",
                entity_id=notification["id"], after={"customerId": customer_id, "runId": run_id, "actionId": action_id},
            )
            return {
                "actionId": action_id, "actionType": action_type, "success": True,
                "detail": "Staff-note draft created.", "orderId": order_id, "notificationId": notification["id"],
            }

        return _reject(f"'{action_type}' has no execution handler.")
    except Exception as exc:
        logger.exception("AI Bakery Manager action execution failed: run=%s action=%s", run_id, action_id)
        record_event(
            actor_id=admin_id, action="agent.action_failed", entity_type="bakery_manager_action",
            entity_id=order_id or customer_id, after={"runId": run_id, "actionId": action_id, "actionType": action_type, "error": str(exc)},
        )
        return {"actionId": action_id, "actionType": action_type, "success": False, "detail": "Action failed unexpectedly — see server logs.", "orderId": order_id, "notificationId": None}


def execute_plan(admin_id: str, run_id: str, actions: list[dict]) -> list[dict]:
    """The manager's checkbox-selected actions only. Each is independently
    re-validated and executed through the exact existing service a human
    action would call — zero Claude calls, zero direct database writes
    from this function itself (order_service/notification_service own
    every write). One action failing never stops the rest of the batch:
    each result is collected and returned individually, never retried.
    """
    return [_execute_one(admin_id, run_id, action) for action in actions]
