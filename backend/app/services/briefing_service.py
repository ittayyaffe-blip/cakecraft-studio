"""AI Daily Briefing service — the Bakery Command Center's centerpiece
screen (Final AI Intelligence Phase). See
docs/FINAL_AI_INTELLIGENCE_PHASE.md "Architecture" for the full write-up.

Composes existing data plus the ML forecast (forecast_service.py) into
one read-only payload: today's orders/revenue, tomorrow's forecast,
pending notifications, high-priority orders, and recommended actions.
Nothing here duplicates another service's query for a *shared* purpose —
_todays_stats() is its own small, independent query (needs total_price,
which dashboard_service's differently-shaped one doesn't select) rather
than a forced-shared one, matching this project's existing convention
(see forecast_service._fetch_order_history's own docstring for the same
reasoning).

Recommended Actions in this phase are rule-based and fully deterministic
(a handful of threshold checks over data already computed for the other
sections) — not LLM-generated. The AI Agent is a later phase in this
project's own incremental rollout plan; building it well requires RAG to
exist first (for grounding), and both are deliberately out of scope
here. What ships instead is already real and useful, and — per this
phase's own Explainable AI requirement — every recommendation already
comes with a plain-English reason baked into its own text.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.core.database import supabase
from app.services import forecast_service, notification_service

logger = logging.getLogger(__name__)


def _fetch_all_orders(columns: str) -> list[dict]:
    """Paginates past PostgREST's default max-rows response cap (1000) —
    caught live once this project's order volume grew past it (the demo
    data scale-up to ~2500 orders; see docs/DATASET_SCALE_UP.md).
    Especially important here: an unpaginated `.select()` isn't
    guaranteed to return the most-recently-created rows within its first
    1000, so "today's" orders could be silently missing entirely, not
    just undercounted. Small, local duplicate of the same fetch-all-pages
    pattern in dashboard_service.py/forecast_service.py — see
    dashboard_service._fetch_all_orders's docstring for why this stays a
    local helper rather than a shared one.
    """
    rows: list[dict] = []
    page_size = 1000
    start = 0
    while True:
        response = supabase.table("orders").select(columns).range(start, start + page_size - 1).execute()
        rows.extend(response.data)
        if len(response.data) < page_size:
            break
        start += page_size
    return rows


def _todays_stats() -> dict:
    """Orders placed today (UTC) and their total revenue. Same "today"
    boundary dashboard_service._get_order_stats() already uses.
    """
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = _fetch_all_orders("created_at, total_price")

    todays_orders = 0
    todays_revenue = 0.0
    for row in rows:
        if datetime.fromisoformat(row["created_at"]) >= today_start:
            todays_orders += 1
            todays_revenue += float(row["total_price"])

    return {"todaysOrders": todays_orders, "todaysRevenue": round(todays_revenue, 2)}


def _high_priority_orders(limit: int = 5) -> list[dict]:
    """Orders needing attention today: not yet completed/cancelled, and
    either (a) due for pickup within the next 48 hours, or (b) a Wedding
    order (inherently higher-stakes/complexity regardless of timing).
    Each comes back with its own plain-English reason.
    """
    response = (
        supabase.table("orders")
        .select("id, status, pickup_date, customers(name), cake_templates(name, category)")
        .in_("status", ["confirmed", "in_progress", "ready"])
        .execute()
    )

    today = datetime.now(timezone.utc).date()
    flagged = []
    for order in response.data:
        reasons = []
        urgency = 1
        pickup_date_str = order.get("pickup_date")
        if pickup_date_str:
            days = (datetime.fromisoformat(pickup_date_str).date() - today).days
            if days <= 0:
                reasons.append("pickup due today or overdue")
                urgency = 3
            elif days <= 2:
                reasons.append(f"pickup due in {days} day{'s' if days != 1 else ''}")
                urgency = 2

        template = order.get("cake_templates") or {}
        if template.get("category") == "Wedding":
            reasons.append("wedding order")
            urgency = max(urgency, 2)

        if reasons:
            flagged.append(
                {
                    "id": order["id"],
                    "customerName": (order.get("customers") or {}).get("name"),
                    "templateName": template.get("name"),
                    "status": order["status"],
                    "reason": "; ".join(reasons).capitalize(),
                    "_urgency": urgency,
                }
            )

    flagged.sort(key=lambda o: -o["_urgency"])
    for order in flagged:
        del order["_urgency"]
    return flagged[:limit]


def _recommended_actions(pending_notification_count: int, high_priority_count: int, forecast: dict) -> list[str]:
    """Rule-based, deterministic recommendations — see module docstring
    for why this phase doesn't hand this to the (not-yet-built) AI Agent.
    """
    actions = []
    if pending_notification_count > 0:
        noun = "notification" if pending_notification_count == 1 else "notifications"
        actions.append(f"Review {pending_notification_count} {noun} awaiting approval in the Notification Queue.")
    if high_priority_count > 0:
        actions.append(f"Check in on {high_priority_count} high-priority order(s) below before end of day.")
    if forecast["workloadLevel"] in ("High", "Very High"):
        actions.append(
            f"Tomorrow looks like a {forecast['workloadLevel'].lower()}-workload day "
            f"({forecast['predictedOrders']} predicted orders) — plan staffing accordingly."
        )
    if not actions:
        actions.append("No urgent items — a good day to get ahead on prep or outreach.")
    return actions


def get_daily_briefing() -> dict:
    """The single entry point the /admin/briefing route calls."""
    todays = _todays_stats()
    forecast = forecast_service.compute_tomorrow_forecast()

    try:
        pending = notification_service.list_notifications(status="awaiting_approval", page=1, page_size=5)
    except Exception:
        logger.exception("Failed to load pending notifications for the daily briefing")
        pending = {"items": [], "total": 0}

    high_priority = _high_priority_orders()
    actions = _recommended_actions(pending["total"], len(high_priority), forecast)

    return {
        "todaysOrders": todays["todaysOrders"],
        "todaysRevenue": todays["todaysRevenue"],
        "forecast": forecast,
        "pendingNotifications": {"total": pending["total"], "items": pending["items"]},
        "highPriorityOrders": high_priority,
        "recommendedActions": actions,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
