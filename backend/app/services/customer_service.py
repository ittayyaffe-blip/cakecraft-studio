"""Customer management service — Epic 1.2 (Customer Management & CRM).

Reads/aggregates the existing `customers` and `orders` tables; writes
nothing (this screen is read-only, per
docs/Bakery_Command_Center_UX_Product_Blueprint_v1.md §6 — no audit event
is logged here because nothing is mutated). Order-domain data is always
fetched through `order_service` rather than queried directly here, and
audit-trail data through `audit_service` — this file composes across those
two domains the same way `dashboard_service.py` already does, it doesn't
duplicate either one's queries.

`get_customer_communications` and `get_customer_ai_insights` are
deliberate placeholders: Gmail/WhatsApp (Master_Blueprint_v1.md §10) and
the AI layer (§9) don't exist yet. Both already return the response shape
their real implementation will use, with `enabled: False` and an empty
list — so the frontend that renders them today needs no changes on the day
either capability actually ships, only these two functions do.

`get_customer_timeline` *does* already include notifications — the
Event-Driven Customer Communication Platform's approval-workflow queue
(see notification_service.py) is a real, live feature this sprint, even
though the channels it will eventually send through are not. A customer's
timeline shows every notification drafted for their orders, at whatever
stage it's currently in (queued/draft/awaiting approval/approved/sent) —
distinct from get_customer_communications, which specifically means "a
message actually delivered through a real channel," still none today.
"""

import re

from app.core.database import supabase
from app.services import audit_service, notification_service, order_service
from app.services.search_utils import sanitize_search_term


def _page_to_range(page: int, page_size: int) -> tuple[int, int]:
    """Same conversion as order_service._page_to_range — 1-based page/size
    to the 0-based, inclusive (start, end) range `.range()` expects.
    Kept local rather than imported: it's two lines of arithmetic with no
    shared state, not worth a cross-module dependency for.
    """
    start = (page - 1) * page_size
    end = start + page_size - 1
    return start, end


def _get_order_stats_for_customers(customer_ids: list[str]) -> dict[str, dict]:
    """Order count, lifetime value, and last-order date per customer id.

    One query for the whole batch, aggregated client-side — the same
    tradeoff `dashboard_service._get_order_stats()` already makes and for
    the same reason: cheap at this project's order volume, and the natural
    place to switch to a server-side aggregate (a Postgres RPC) if that
    ever stops being true is right here, not spread across callers.
    """
    if not customer_ids:
        return {}

    response = (
        supabase.table("orders")
        .select("customer_id, total_price, created_at")
        .in_("customer_id", customer_ids)
        .execute()
    )

    stats: dict[str, dict] = {}
    for row in response.data:
        entry = stats.setdefault(
            row["customer_id"],
            {"orderCount": 0, "lifetimeValue": 0.0, "lastOrderDate": None},
        )
        entry["orderCount"] += 1
        entry["lifetimeValue"] += row["total_price"]
        if entry["lastOrderDate"] is None or row["created_at"] > entry["lastOrderDate"]:
            entry["lastOrderDate"] = row["created_at"]

    return stats


def list_customers(search: str | None = None, page: int = 1, page_size: int = 20) -> dict:
    """Search/paginate customers, each row enriched with order stats."""
    query = supabase.table("customers").select("*", count="exact")

    if search:
        safe_search = sanitize_search_term(search)
        if not safe_search:
            return {"items": [], "total": 0, "page": page, "pageSize": page_size}
        query = query.or_(
            f"name.ilike.%{safe_search}%,email.ilike.%{safe_search}%,phone.ilike.%{safe_search}%"
        )

    start, end = _page_to_range(page, page_size)
    response = query.order("created_at", desc=True).range(start, end).execute()
    customers = response.data

    stats_by_customer = _get_order_stats_for_customers([c["id"] for c in customers])
    default_stats = {"orderCount": 0, "lifetimeValue": 0.0, "lastOrderDate": None}
    items = [{**c, **stats_by_customer.get(c["id"], default_stats)} for c in customers]

    return {
        "items": items,
        "total": response.count or 0,
        "page": page,
        "pageSize": page_size,
    }


def get_customer_by_id(customer_id: str) -> dict | None:
    """Raw customer row, no computed stats — the cheap existence check
    every /admin/customers/{id}/... sub-resource route uses before doing
    its own, potentially more expensive, work.
    """
    response = (
        supabase.table("customers").select("*").eq("id", customer_id).maybe_single().execute()
    )
    return response.data if response is not None else None


def find_customer_by_email(email: str) -> tuple[dict | None, bool]:
    """Read-only customer identification for an inbound Email message
    (Step 3 — see inbound_service.py). Unlike order_service.
    _find_or_create_customer, this never creates a row: an inbound
    message from an address we don't recognize means "unknown customer",
    not "invent one" — the inbound message stays visible to staff either
    way (see the migration's own note on customer_id being nullable).

    Returns (customer, is_ambiguous). This project's schema has no unique
    constraint on customers.email, so more than one row sharing the same
    address is a real, if rare, possibility — is_ambiguous=True with
    customer=None means "don't guess which one", the same caution
    find_open_order_for_customer applies to multiple open orders.
    """
    response = supabase.table("customers").select("*").eq("email", email).execute()
    if len(response.data) == 1:
        return response.data[0], False
    return None, len(response.data) > 1


def find_customer_by_phone(phone: str) -> tuple[dict | None, bool]:
    """Same contract as find_customer_by_email, keyed on phone — matched
    on the digits-only normalized form (mirrors communication.
    whatsapp_adapter._to_whatsapp_number's own normalization) since
    customers.phone is free-text and not guaranteed consistently
    formatted at write time.

    Fetches every customer and filters in Python rather than a SQL
    predicate: normalizing phone formatting at the database layer would
    need a generated column or extension this schema doesn't have, and at
    this project's scale (~100 demo customers) a full-table read is a
    reasonable, simple tradeoff — flagged here as a known ceiling, not an
    oversight, for whenever real customer volume would call for it.
    """
    normalized = re.sub(r"\D", "", phone)
    if not normalized:
        return None, False
    response = supabase.table("customers").select("*").execute()
    matches = [c for c in response.data if c.get("phone") and re.sub(r"\D", "", c["phone"]) == normalized]
    if len(matches) == 1:
        return matches[0], False
    return None, len(matches) > 1


def get_customer_detail(customer_id: str) -> dict | None:
    """Customer profile: the raw row plus the same order stats the list
    screen shows, so the numbers on the profile header always match what
    the list screen would have shown for this customer.
    """
    customer = get_customer_by_id(customer_id)
    if customer is None:
        return None

    default_stats = {"orderCount": 0, "lifetimeValue": 0.0, "lastOrderDate": None}
    stats = _get_order_stats_for_customers([customer_id]).get(customer_id, default_stats)
    return {**customer, **stats}


def get_customer_timeline(customer_id: str) -> list[dict]:
    """A single chronological feed of everything that's happened for this
    customer: every order they placed, every status change any of those
    orders went through (reusing Epic 1's audit trail instead of a
    dedicated history table — see order_service.get_orders_for_customer
    and audit_service.list_events_for_entities), and every notification
    drafted for those orders (notification_service.list_notifications_for_customer)
    at whatever stage it's currently at.
    """
    orders = order_service.get_orders_for_customer(customer_id)
    order_ids = [order["id"] for order in orders]
    status_events = audit_service.list_events_for_entities("orders", order_ids)
    notifications = notification_service.list_notifications_for_customer(customer_id)

    timeline: list[dict] = []

    for order in orders:
        template = order.get("cake_templates")
        timeline.append(
            {
                "type": "order_placed",
                "timestamp": order["created_at"],
                "orderId": order["id"],
                "templateName": template["name"] if template else None,
                "status": order["status"],
                "before": None,
                "after": None,
                "actorName": None,
                "label": None,
                "notificationId": None,
            }
        )

    for event in status_events:
        actor = event.get("staff_profiles")
        timeline.append(
            {
                "type": event["action"],
                "timestamp": event["created_at"],
                "orderId": event["entity_id"],
                "templateName": None,
                "status": None,
                "before": event.get("before"),
                "after": event.get("after"),
                "actorName": actor["name"] if actor else "System",
                "label": None,
                "notificationId": None,
            }
        )

    for notification in notifications:
        timeline.append(
            {
                "type": "notification",
                "timestamp": notification["created_at"],
                "orderId": notification["order_id"],
                "templateName": None,
                "status": notification["status"],
                "before": None,
                "after": None,
                "actorName": None,
                "label": notification_service.get_event_label(notification["event"]),
                "notificationId": notification["id"],
            }
        )

    timeline.sort(key=lambda item: item["timestamp"], reverse=True)
    return timeline


def get_customer_communications(customer_id: str) -> dict:
    """Placeholder until Gmail/WhatsApp integration exists
    (Master_Blueprint_v1.md §10, Phase 4 — 'notifications_log'). Always
    returns `enabled: False` and an empty list today; when that phase
    ships, this function starts querying `notifications_log` filtered to
    this customer's orders and flips `enabled` to True — the response
    shape doesn't change, so nothing calling this needs to change either.
    """
    return {"enabled": False, "items": []}


def get_customer_ai_insights(customer_id: str) -> dict:
    """Placeholder until the AI layer exists (Master_Blueprint_v1.md §9,
    Phases 6-7 — churn flags, order-pattern summaries). Same extensibility
    approach as get_customer_communications: real insights will populate
    `insights` and flip `enabled` to True without changing this shape.
    """
    return {"enabled": False, "insights": []}
