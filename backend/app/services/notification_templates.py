"""Static notification templates — Event-Driven Customer Communication
Platform (see docs/SPRINT1_EVENT_DRIVEN_COMMUNICATION.md).

One template per order status that's actually customer-relevant.
Step 5 added `pending` (order received): the confirmation page already
reassures the customer at submission time, but that's a one-time page
view, not a durable, human-reviewable communication record — this
template gives "we received your order" the same draft -> approve -> send
treatment every other stage already gets, rather than being the one stage
with no Communications Workspace record at all.

`render()` is deterministic string substitution today. It is the single,
deliberate seam a future AI-assisted drafting step
(`docs/Bakery_Command_Center_UX_Product_Blueprint_v1.md` §11's "Message
draft assistant") is designed to replace: `notification_service.py` only
ever calls `get_template_for_status` + `render`, never touches template
text itself, so swapping this function's implementation later — e.g. for
an LLM call grounded in the same order/customer context — changes nothing
about creation, approval, or sending.
"""

# Keyed by `orders.status` (the real, existing 6-value enum — see
# order_service.ORDER_STATUSES). `event` is the semantic name stored on
# the notification row; it's intentionally decoupled from the order
# status string so a future, more granular production stage (e.g. a
# "Decorating Started" sub-stage that doesn't exist as an order status
# today) could add its own entry here without those two vocabularies
# needing to match 1:1.
ORDER_STATUS_EVENT_TEMPLATES = {
    "pending": {
        "event": "order_received",
        "label": "Order Received",
        "subject": "We've received your order!",
        "body": (
            "Hi {customer_name}, thank you for your order — we've received your "
            "request for {template_name} and our team will review the details "
            "shortly."
        ),
    },
    "confirmed": {
        "event": "order_confirmed",
        "label": "Order Confirmed",
        "subject": "Your order has been confirmed!",
        "body": (
            "Hi {customer_name}, great news — your order for {template_name} has "
            "been confirmed.{pickup_line} We'll keep you posted as we bring it to life."
        ),
    },
    "in_progress": {
        "event": "baking_started",
        "label": "Baking Started",
        "subject": "We've started working on your cake!",
        "body": (
            "Hi {customer_name}, our bakers have started on your {template_name}. "
            "It's in good hands!"
        ),
    },
    "ready": {
        "event": "ready_for_pickup",
        "label": "Ready for Pickup",
        "subject": "Your cake is ready for pickup!",
        "body": (
            "Hi {customer_name}, your {template_name} is ready whenever you are. "
            "See you soon!"
        ),
    },
    "completed": {
        "event": "order_completed",
        "label": "Completed",
        "subject": "Thank you for your order!",
        "body": (
            "Hi {customer_name}, thank you for choosing Maison de Gâteau Paris for "
            "your {template_name}. We hope you loved it!"
        ),
    },
    "cancelled": {
        "event": "order_cancelled",
        "label": "Order Cancelled",
        "subject": "Your order has been cancelled",
        "body": (
            "Hi {customer_name}, your order for {template_name} has been "
            "cancelled. Reach out any time if you have questions."
        ),
    },
}

# event key -> human label, e.g. for the Customer Timeline
# (customer_service.get_customer_timeline) to describe a notification
# entry without needing to know the templates dict's shape.
EVENT_LABELS = {t["event"]: t["label"] for t in ORDER_STATUS_EVENT_TEMPLATES.values()}


def get_template_for_status(order_status: str) -> dict | None:
    """The template for one order status, or None if that status has no
    customer-relevant message."""
    return ORDER_STATUS_EVENT_TEMPLATES.get(order_status)


def render(template: dict, order: dict) -> dict:
    """Fill a template's subject/body placeholders from an order (and its
    joined customer/template — see order_service._ORDER_DETAIL_SELECT,
    the same embedded shape this expects).

    `pickup_line` is a real fact or nothing — never invented. Today's
    order-creation flow never actually sets `orders.pickup_date` (no admin
    route writes it either; only tools/demo_data_seed.py backdates it for
    historical demo orders), so this is almost always the empty string in
    practice — the templates below are written to read cleanly either way,
    not to assume a date exists. Only "confirmed" uses it: by the time an
    order is confirmed, a pickup date being announced reads as a real
    commitment worth stating; "ready" deliberately stays date-free (see its
    own template) since restating a pickup date on a cake that's ready *now*
    could as easily read as a future promise as a completed fact.
    """
    customer = order.get("customers") or {}
    cake_template = order.get("cake_templates") or {}
    pickup_date = order.get("pickup_date")
    pickup_line = f" Your pickup date is {pickup_date}." if pickup_date else ""

    return {
        "subject": template["subject"],
        "body": template["body"].format(
            customer_name=customer.get("name") or "there",
            template_name=cake_template.get("name") or "your cake",
            pickup_line=pickup_line,
        ),
    }
