"""Request/response schemas for the customer-facing website chat widget
(app/api/routes/chat.py) -- plain Q&A (/ask) and the chat-assisted
ordering MVP (/order, see agent_service.run_order_assistant_turn).
"""

from pydantic import BaseModel


class ChatAskRequest(BaseModel):
    name: str
    email: str
    question: str
    # Purely a hint for the frontend's own convenience -- the route never
    # trusts this for grounding: which order (if any) is used comes from
    # order_service.find_open_order_for_customer, derived server-side from
    # the identified customer, so a client can never point the AI at
    # someone else's order by passing an arbitrary id here.
    orderId: str | None = None


class ChatAskResponse(BaseModel):
    answer: str
    # Step 3B's existing intent classification (agent_service.INTENTS),
    # already computed for every /ask call -- surfaced here purely so the
    # widget can offer a "Start an order?" nudge when it's
    # "NEW_ORDER_INQUIRY", without a second classification call. Never
    # drives anything server-side by itself; the customer still has to
    # explicitly opt in (see /order below) before any order-related state
    # exists at all.
    intent: str | None = None


class ChatOrderDraft(BaseModel):
    """The order-in-progress, round-tripped by the client turn to turn --
    this project's chat endpoints are already stateless server-side (see
    chat-widget.js's own note on why chat alone keeps client-side
    session state), so this is the same pattern extended to hold
    "what's been selected so far" rather than inventing server-side
    session storage for one feature. Every field is nullable/omittable:
    an unset field simply hasn't been collected yet.
    """

    templateId: str | None = None
    cakeSizeId: str | None = None
    flavorId: str | None = None
    fillingId: str | None = None
    frostingId: str | None = None
    phone: str | None = None
    # Pickup Date + Order Priority, Phase 2: optional, opportunistic --
    # never required to confirm a chat order (see run_order_assistant_
    # turn's own note on why this stays additive rather than a hard gate,
    # unlike the Website form). ISO "YYYY-MM-DD"/"HH:MM" strings, always
    # independently re-validated server-side before ever reaching
    # order_service.create_order() -- never trusted just because Claude
    # proposed them, same posture as every other extracted field here.
    pickupDate: str | None = None
    pickupTime: str | None = None
    # Free text, e.g. "ready by tomorrow?" -- never required, never id-
    # validated, just carried through to the created order's `notes`
    # field (see agent_service._order_assistant_prompt's own note on
    # rush/availability questions never being promised, only recorded).
    specialRequestNote: str | None = None
    # Deterministic conversational state, never Claude-guessed -- true
    # exactly when the previous turn's reply was the final "shall I place
    # this order?" ask (see agent_service._normalize_order_draft's own
    # note). Lets a short, unambiguous affirmative reply confirm without
    # depending solely on Claude's own confirmedNow judgment.
    awaitingOrderConfirmation: bool = False


class ChatOrderRequest(BaseModel):
    name: str
    email: str
    message: str
    draft: ChatOrderDraft | None = None
    # The ONE customer message that made the widget offer "Start an
    # order?" in the first place (see ChatAskResponse.intent) -- sent
    # once, by the widget itself, only on the very first ordering turn
    # (empty/absent on every later one). Not a broad conversation-
    # history import: agent_service.run_order_assistant_turn only ever
    # consults it to try mapping an already-stated guest count to a real
    # cake size, via a deterministic catalog lookup, before Claude is
    # even called -- see that function's own docstring.
    triggerContext: str | None = None


class ChatOrderResponse(BaseModel):
    reply: str
    draft: ChatOrderDraft
    orderCreated: bool
    orderId: str | None = None
