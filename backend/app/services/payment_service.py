"""Simulated/demo payment service -- a university-project stand-in for a
real payment provider. No card number, CVV, expiry, or any real financial
credential is ever collected or stored anywhere in this project; see
supabase/migrations/20260812090000_create_payments.sql.

One `payments` row per order (`unique(order_id)`). Website, Chat, and
WhatsApp all reach the exact same simulate_payment() below through the
exact same POST /orders/{id}/pay route (app/api/routes/orders.py) -- no
channel has its own payment logic, matching how they already share one
order_service.create_order() for order creation.

Payment is a separate, explicit customer action from order confirmation
(see run_order_assistant_turn's own note) -- nothing in this module is
ever called automatically right after an order is created.
"""

import logging
import secrets
from datetime import datetime, timezone

from app.core.database import supabase
from app.services import audit_service, notification_service, order_service

logger = logging.getLogger(__name__)

PAYMENT_STATUSES = ("pending", "paid", "failed")


class OrderNotFoundError(Exception):
    """No order exists for the given id -- the route maps this to 404."""


class OrderNotPayableError(Exception):
    """The order exists but is not in a payable state (e.g. cancelled) --
    the route maps this to 400."""


def _generate_simulated_reference() -> str:
    """A clearly fake, clearly non-financial demo reference -- never
    anything resembling a real transaction/authorization id from an
    actual payment provider."""
    return f"SIM-{secrets.token_hex(6).upper()}"


def get_payment_for_order(order_id: str) -> dict | None:
    """Read-only lookup -- no side effects, safe to call just to check
    status (e.g. for AI grounding or the Back Office order detail view).
    None means no payment has been initiated for this order yet.
    """
    response = supabase.table("payments").select("*").eq("order_id", order_id).maybe_single().execute()
    return response.data if response is not None else None


def get_or_create_payment(order_id: str, amount: float) -> dict:
    """The one payment row for this order -- created lazily, from *this*
    order's own authoritative total_price, on first touch. Mirrors
    order_service.find_or_create_customer's own get-or-create shape.
    """
    existing = get_payment_for_order(order_id)
    if existing is not None:
        return existing

    created = supabase.table("payments").insert(
        {"order_id": order_id, "status": "pending", "amount": amount}
    ).execute()
    return created.data[0]


def simulate_payment(order_id: str) -> dict:
    """The ONE simulated-payment entry point every channel calls (see
    this module's own docstring).

    Amount is ALWAYS `orders.total_price` -- never accepted from any
    caller, so no client/Chat/WhatsApp/Claude-supplied number can ever
    become what a customer is charged (simulated or not).

    Idempotent: a retry, a double click, a duplicate Chat/WhatsApp event
    for an order already paid returns the existing successful payment
    unchanged -- never a second (conceptual) charge, never a second
    pending -> confirmed transition, never a second notification. Two
    layers make this true even under a race (two near-simultaneous calls
    for the same order): the already-paid short-circuit below catches a
    sequential retry, and the conditional UPDATE (`.eq("status",
    "pending")`) ensures only one concurrent caller ever actually flips
    the row and runs the confirm+notify side effects -- the other re-reads
    and returns the same, already-successful result.

    Raises OrderNotFoundError / OrderNotPayableError for the route to map
    to a clean 404/400 -- same "service validates, route maps to HTTP"
    shape order_service.update_order_status already established.

    Returns {"payment": dict, "order_status": str}.
    """
    order = order_service.get_order_by_id(order_id)
    if order is None:
        raise OrderNotFoundError(order_id)
    if order["status"] == "cancelled":
        raise OrderNotPayableError("This order has been cancelled and cannot be paid")

    payment = get_or_create_payment(order_id, order["total_price"])

    if payment["status"] == "paid":
        return {"payment": payment, "order_status": order["status"]}

    updated = (
        supabase.table("payments")
        .update({
            "status": "paid",
            "paid_at": datetime.now(timezone.utc).isoformat(),
            "simulated_reference": _generate_simulated_reference(),
        })
        .eq("order_id", order_id)
        .eq("status", "pending")  # optimistic lock -- see the idempotency note above
        .execute()
    )

    if not updated.data:
        # Lost a race with a concurrent identical call for this same order --
        # someone else's request already flipped this row to "paid" between
        # our read and write. Re-read rather than treat this as a failure:
        # the outcome (paid, exactly once) is exactly what both callers wanted.
        payment = get_payment_for_order(order_id)
        return {"payment": payment, "order_status": order_service.get_order_by_id(order_id)["status"]}

    payment = updated.data[0]
    order_status = order["status"]

    # The one automatic status transition in this project: pending ->
    # confirmed, on successful payment, no staff approval. Never touches
    # any later production stage (in_progress/ready/completed) -- those
    # stay staff-driven via the existing admin status-update route.
    if order_status == "pending":
        updated_order = order_service.update_order_status(order_id, "confirmed")
        order_status = updated_order["status"]
        audit_service.record_event(
            actor_id=None,  # system-initiated -- no staff member acted (see record_event's own docstring)
            action="order.payment_confirmed",
            entity_type="orders",
            entity_id=order_id,
            before={"status": "pending"},
            after={"status": "confirmed"},
        )
        try:
            # Reuses the exact same notification path the admin status-
            # update route already goes through -- no second notification
            # system, no new template, human-in-the-loop for the actual
            # send is unchanged (still a `draft` a staff member submits).
            notification_service.create_notification_for_order_event(updated_order, "confirmed")
        except Exception:
            logger.exception("Failed to draft confirmed-order notification for order=%s", order_id)

    return {"payment": payment, "order_status": order_status}
