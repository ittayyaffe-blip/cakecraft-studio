"""Deterministic order-priority scoring — a pure, Claude-free operational
decision-support signal. READ ONLY: this module never writes to the
database, never changes an order's status, and is never called during
order creation/status-update/payment/notification flows — only by the
admin Orders routes (to display it) and, in a later phase, AI Bakery
Manager (to help bound its candidate set). See docs/FINAL_ARCHITECTURE.md
for the Solution-Architect-approved policy this implements verbatim.

No Anthropic/anthropic import anywhere in this file, on purpose — the same
order always gets the same priority from the same facts, computed by
ordinary Python, never by an LLM. This is an extraction and formalization
of urgency signals already proven live in briefing_service.
_high_priority_orders() (the "pickup within 2 days" window) and
bakery_manager_service._production_start_eligibility() (the same window,
applied to the advance_to_in_progress gate) — not a competing new model.
The one deliberate departure from those two functions: a Wedding-category
boost here only fires for a still-CONFIRMED order (production not started
yet), narrower than _high_priority_orders()'s "any Wedding, any status" —
a considered policy refinement, not an oversight.

compute_priority()'s `priority=None` covers two genuinely different cases,
kept deliberately distinct (never conflated into one "unknown" bucket):
  - the order is outside this policy's scope entirely (still `pending` —
    not yet reviewed/confirmed, so there's nothing to prioritize for
    production yet — or already `completed`/`cancelled`) —
    manager_attention=False, nothing to flag.
  - the order IS in scope (confirmed/in_progress/ready) but is missing
    the one fact priority depends on (pickup_date) — manager_attention=
    True. This is an EXCEPTION (missing information), not a priority
    level: urgency is never inferred/guessed when the underlying fact is
    absent. A missing pickup date must never silently become CRITICAL.
"""

from datetime import datetime, timezone

# Same "due soon" window already live in briefing_service._high_priority_orders()
# and bakery_manager_service._production_start_eligibility() -- reused, not
# reinvented, for exactly the reasons those two functions already give.
_HIGH_PRIORITY_WITHIN_DAYS = 2

_ACTIVE_PRODUCTION_STATUSES = frozenset({"confirmed", "in_progress", "ready"})

_MISSING_PICKUP_DATE_REASON = "Pickup date missing — priority cannot be determined."


def compute_priority(order: dict) -> dict:
    """Returns {"priority": "CRITICAL" | "HIGH" | "NORMAL" | "LOW" | None,
    "reason": str, "manager_attention": bool}.

    Expects the same order dict shape order_service.list_orders()/
    get_order_by_id() already return (top-level `status`/`pickup_date`,
    nested `cake_templates.category`) -- no extra query, no new field.
    """
    status = order.get("status")

    if status not in _ACTIVE_PRODUCTION_STATUSES:
        return {
            "priority": None,
            "reason": f"No production priority — order is {status}.",
            "manager_attention": False,
        }

    pickup_date = order.get("pickup_date")
    if not pickup_date:
        return {"priority": None, "reason": _MISSING_PICKUP_DATE_REASON, "manager_attention": True}

    try:
        days_out = (datetime.fromisoformat(pickup_date).date() - datetime.now(timezone.utc).date()).days
    except ValueError:
        return {
            "priority": None,
            "reason": f"pickup_date '{pickup_date}' could not be parsed.",
            "manager_attention": True,
        }

    if days_out <= 0:
        reason = "Pickup is overdue." if days_out < 0 else "Pickup is today."
        return {"priority": "CRITICAL", "reason": reason, "manager_attention": True}

    if days_out <= _HIGH_PRIORITY_WITHIN_DAYS:
        day_word = "day" if days_out == 1 else "days"
        return {
            "priority": "HIGH",
            "reason": f"Pickup in {days_out} {day_word} — within the production-start window.",
            "manager_attention": False,
        }

    category = (order.get("cake_templates") or {}).get("category")
    if status == "confirmed" and category == "Wedding":
        return {
            "priority": "HIGH",
            "reason": "Confirmed Wedding order — production scheduling needs attention regardless of exact pickup timing.",
            "manager_attention": False,
        }

    if status == "ready":
        return {
            "priority": "LOW",
            "reason": f"Ready and awaiting pickup in {days_out} days — comfortable buffer, no action needed.",
            "manager_attention": False,
        }

    return {
        "priority": "NORMAL",
        "reason": f"Pickup in {days_out} days — on track, normal production workflow.",
        "manager_attention": False,
    }
