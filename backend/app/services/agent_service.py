"""AI Operations Agent — Business Intelligence Layer. See
docs/BUSINESS_INTELLIGENCE_LAYER.md "AI Agent Design" for the full
write-up.

Combines live operational data (briefing_service), the ML forecast
(forecast_service, via briefing_service), and bakery knowledge
(rag_service) into three concrete, bounded capabilities:

  - generate_morning_briefing() — a synthesized operational narrative
    (production/staffing/inventory notes) on top of the existing AI
    Daily Briefing's structured data.
  - ask_operations_question(question) — the general "what should I
    prepare tomorrow?" entry point: live data + forecast + retrieved
    bakery knowledge, synthesized into one grounded recommendation.
  - draft_customer_communication(order_id, instruction, channel) —
    drafts a customer message for the staff-selected channel
    (email/whatsapp) and inserts it as a `draft` notification, reusing
    the *existing* Notification Engine's table/lifecycle exactly as-is
    (no changes to notification_service.py — see the function's own
    docstring for why the insert happens here directly).

Human-in-the-loop, structurally, not by convention: nothing in this
module ever calls notification_service.send() or any Communication
Adapter. Every draft this Agent produces lands in the existing
Notification Queue at `draft` status, going through the same
submit -> approve -> send workflow a staff-authored draft already does
— the Agent recommends and drafts, staff decides.
"""

import json
import logging

import anthropic

from app.core.config import settings
from app.core.database import supabase
from app.services import briefing_service, order_service, rag_service

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"


def is_configured() -> bool:
    return bool(settings.anthropic_api_key)


def _claude(prompt: str, max_tokens: int = 700) -> str:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    # Extended thinking is on by default for claude-sonnet-5 and counts
    # against max_tokens — for straightforward "synthesize this
    # structured data into a paragraph" tasks it added latency/cost with
    # no benefit, and at a modest max_tokens budget left no room for the
    # actual answer (caught live: a 500-token budget was consumed
    # entirely by thinking, leaving zero text blocks in the response).
    response = client.messages.create(
        model=_MODEL, max_tokens=max_tokens, thinking={"type": "disabled"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            return block.text
    raise ValueError("Claude response contained no text block")


def _parse_json_response(text: str) -> dict | None:
    """Claude is asked for a JSON object; this tolerates it wrapping the
    JSON in a markdown code fence or surrounding prose (common model
    habits) by extracting the outermost `{...}` span rather than
    assuming the whole response is clean JSON, then gives up and returns
    None — which callers treat as "fall back to the raw text" rather
    than crash. None is also the correct outcome for a genuinely
    truncated response (hit max_tokens mid-object): an incomplete `{...}`
    still fails to parse, exactly as it should.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None


def _not_configured_response(narrative: str) -> dict:
    return {
        "narrative": narrative,
        "productionNotes": None,
        "staffingNotes": None,
        "inventoryNotes": None,
        "sources": [],
    }


def generate_morning_briefing() -> dict:
    """A synthesized operational narrative on top of the existing AI
    Daily Briefing (briefing_service.get_daily_briefing(), reused
    unchanged) — the "explain what the numbers mean" layer this phase
    adds. Retrieves bakery-knowledge context relevant to daily
    production/staffing so the narrative can ground its suggestions
    (e.g., citing the Bakery Operations Manual's staffing thresholds)
    rather than inventing generic advice.
    """
    briefing = briefing_service.get_daily_briefing()

    if not is_configured():
        logger.info("Morning briefing narrative skipped: Anthropic API is not configured")
        return _not_configured_response(
            "Today's AI insights aren't available right now — the structured "
            "forecast, high-priority orders, and recommended actions above "
            "still reflect today's real data."
        )

    knowledge = rag_service.retrieve(
        "daily production scheduling, staffing levels, and workload planning", top_k=3
    )
    knowledge_context = "\n\n".join(f"[{c['title']}]\n{c['content']}" for c in knowledge)

    prompt = f"""You are the AI Operations Agent for Maison de Gâteau Paris, a bakery.
Write this morning's operational briefing for the head baker using the live data below.
Respond with ONLY a JSON object, no other text, in this exact shape:
{{"narrative": "2-3 sentence plain-English summary of the day, in the style of a knowledgeable colleague, not a report",
  "productionNotes": "what to prioritize in production today/tomorrow",
  "staffingNotes": "any staffing adjustment worth considering, or 'No change needed' if none",
  "inventoryNotes": "any ingredient/supply consideration implied by the forecast or high-priority orders, or 'Nothing unusual' if none"}}

LIVE DATA:
- Today: {briefing['todaysOrders']} orders, ${briefing['todaysRevenue']:.2f} revenue
- Tomorrow's forecast: {briefing['forecast']['predictedOrders']} orders, ${briefing['forecast']['predictedRevenue']:.2f} revenue, {briefing['forecast']['workloadLevel']} workload, {briefing['forecast']['confidence']}% confidence. Reason: {briefing['forecast']['reason']}
- Pending notifications awaiting approval: {briefing['pendingNotifications']['total']}
- High priority orders: {json.dumps(briefing['highPriorityOrders'])}

RELEVANT BAKERY KNOWLEDGE:
{knowledge_context}"""

    try:
        raw = _claude(prompt)
        parsed = _parse_json_response(raw)
        if parsed is None:
            return _not_configured_response(raw)
        parsed["sources"] = [{"title": c["title"], "sourceFile": c["source_file"]} for c in knowledge]
        return parsed
    except Exception:
        logger.exception("Morning briefing generation failed")
        return _not_configured_response(
            "We couldn't generate today's AI narrative just now — the "
            "structured data above still reflects today's real numbers."
        )


def ask_operations_question(question: str) -> dict:
    """The general-purpose Agent entry point — "What should I prepare
    tomorrow?" and similar. Combines live operational data (today's
    stats, the ML forecast, high-priority orders — all from
    briefing_service, not re-derived) with retrieved bakery knowledge
    (rag_service), synthesized by Claude into one grounded, explained
    recommendation. This is the literal implementation of this phase's
    "Final Demonstration" scenario.
    """
    briefing = briefing_service.get_daily_briefing()
    knowledge = rag_service.retrieve(question, top_k=4)

    if not is_configured():
        logger.info("Agent question answering skipped: Anthropic API is not configured")
        return {
            "answer": "Our AI assistant isn't available right now — see the AI Daily Briefing above for today's forecast and priorities.",
            "sources": [],
        }

    knowledge_context = "\n\n".join(f"[{c['title']}]\n{c['content']}" for c in knowledge)
    prompt = f"""You are the AI Operations Agent for Maison de Gâteau Paris, a bakery.
Answer the head baker's question below using the live operational data and bakery knowledge provided.
Be concrete and specific (mention actual numbers, order names/categories, or policy details from the
data given) — never a vague generic answer. If the data doesn't cover something, say so plainly.

LIVE OPERATIONAL DATA:
- Today: {briefing['todaysOrders']} orders, ${briefing['todaysRevenue']:.2f} revenue
- Tomorrow's forecast: {briefing['forecast']['predictedOrders']} orders, ${briefing['forecast']['predictedRevenue']:.2f} revenue, {briefing['forecast']['workloadLevel']} workload, {briefing['forecast']['confidence']}% confidence. Reason: {briefing['forecast']['reason']}
- High priority orders: {json.dumps(briefing['highPriorityOrders'])}
- Pending notifications awaiting approval: {briefing['pendingNotifications']['total']}

RELEVANT BAKERY KNOWLEDGE:
{knowledge_context}

QUESTION: {question}"""

    try:
        answer = _claude(prompt, max_tokens=500)
    except Exception:
        logger.exception("Agent question answering failed for: %s", question)
        answer = "We couldn't answer that just now — see the AI Daily Briefing above for today's data."

    sources = [{"title": c["title"], "sourceFile": c["source_file"]} for c in knowledge]
    return {"answer": answer, "sources": sources}


VALID_CHANNELS = ("email", "whatsapp")


def draft_customer_communication(
    order_id: str, instruction: str | None = None, channel: str | None = None
) -> dict:
    """Drafts a customer message for a specific order and inserts it
    directly into `notifications` at `draft` status — the exact same
    table/shape/lifecycle `notification_service.create_notification_for_
    order_event` already uses, just a different creation entry point (an
    on-demand Agent request instead of an order-status transition).
    notification_service.py itself is not modified: the insert happens
    here, in the Agent's own module, so the existing engine stays
    untouched while still producing rows the existing Notification
    Queue UI, approval workflow, and Communication Adapters already know
    how to handle without any changes there either.

    `channel` is the staff's explicit Email/WhatsApp choice from the
    Order Detail drawer — defaults to "email" for backward compatibility
    with callers that predate this parameter. Validated strictly here,
    independently of the route's own check (see admin/agent.py), so this
    function is safe called directly too. This is the *only* place
    `channel` is decided: it never reaches the Claude prompt below and
    Claude's response is never consulted for it, the same way
    `status="draft"` in the insert payload isn't something Claude's
    output can influence either — both are hardcoded from validated
    inputs, not parsed from the model's text.

    Raises ValueError if `channel` isn't one of VALID_CHANNELS, or if the
    order doesn't exist — the route turns both into a clean HTTP error
    (400 and 404 respectively; see admin/agent.py). Channel is validated
    first, before the order lookup or any Claude/RAG call, so an invalid
    request fails fast without unnecessary work.
    """
    channel = channel or "email"
    if channel not in VALID_CHANNELS:
        raise ValueError(f"Invalid channel: {channel!r} (must be one of {VALID_CHANNELS})")

    order = order_service.get_order_by_id(order_id)
    if order is None:
        raise ValueError(f"No order found with id={order_id}")

    if not is_configured():
        # The RuntimeError's own message becomes the HTTP error `detail`
        # the admin UI shows verbatim (see admin/agent.py's route) — kept
        # free of any technical/env-var detail on purpose; that detail is
        # logged here, server-side only.
        logger.warning("Draft communication requested but Anthropic API is not configured")
        raise RuntimeError("Our AI assistant isn't available right now — please try again later or draft this message manually.")

    customer = order.get("customers") or {}
    template = order.get("cake_templates") or {}
    knowledge = rag_service.retrieve(instruction or "customer communication tone and policy", top_k=2)
    knowledge_context = "\n\n".join(f"[{c['title']}]\n{c['content']}" for c in knowledge)

    prompt = f"""You are drafting a customer email for Maison de Gâteau Paris, a bakery, following the
house tone: warm, personal, and specific (see Customer Service Handbook). Respond with ONLY a JSON
object: {{"subject": "...", "body": "..."}}

ORDER CONTEXT:
- Customer: {customer.get('name', 'the customer')}
- Cake: {template.get('name', 'their cake')} ({template.get('category', '')})
- Order status: {order.get('status')}
- Staff instruction: {instruction or "Write a friendly, relevant update for this order."}

RELEVANT BAKERY KNOWLEDGE:
{knowledge_context}"""

    # 400 wasn't enough for a full JSON-wrapped multi-paragraph email —
    # caught live: the response got cut off mid-body, producing invalid
    # JSON that silently fell back to the raw (still-truncated,
    # still-fenced) text as the notification body.
    raw = _claude(prompt, max_tokens=800)
    parsed = _parse_json_response(raw)
    subject = parsed["subject"] if parsed else "An update on your order"
    body = parsed["body"] if parsed else raw

    payload = {
        "order_id": order["id"],
        "customer_id": order["customer_id"],
        "event": "agent_drafted",
        "status": "draft",
        "channel": channel,
        "subject": subject,
        "body": body,
    }
    response = supabase.table("notifications").insert(payload).execute()
    return response.data[0]
