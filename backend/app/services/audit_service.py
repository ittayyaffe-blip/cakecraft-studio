"""Audit logging service — the single place that writes to `public.audit_log`.

`record_event` is intentionally generic: Phase 1 only calls it for admin
login and logout (`app/api/routes/admin/auth.py`), but it's the framework
every *future* admin action (catalog edit, order status change, etc.) is
meant to call too — nothing else should insert into `audit_log` directly.

A failed audit write is logged, not raised: the admin action it describes
must still succeed even if audit logging itself is temporarily unavailable
(fail open, not closed — a missed log line is recoverable, a login a staff
member can't complete because logging hiccuped is a worse outcome).
"""

import logging

from app.core.database import supabase

logger = logging.getLogger(__name__)


def record_event(
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    *,
    created_at: str | None = None,
) -> None:
    """Append one row to `audit_log`.

    Args:
        actor_id: the acting staff member's id (`staff_profiles.user_id`).
            Nullable for system-initiated events — none exist yet, but the
            column allows for them later without a schema change.
        action: a short, dotted event name, e.g. `"admin.login"`,
            `"admin.logout"`; future actions follow the same
            `"<entity>.<verb>"` convention, e.g. `"order.status_changed"`.
        entity_type: the kind of thing acted on, e.g. `"staff_profiles"`,
            future: `"orders"`, `"cake_templates"`.
        entity_id: the specific row's id, if any.
        before / after: optional snapshots of the changed entity, for
            actions that mutate something (login/logout have neither).
        created_at: keyword-only override used exclusively by
            tools/demo_data_seed.py, so a seeded order's audit trail reads
            as having happened over time rather than all at once during
            seeding (see docs/SPRINT2_DEMO_DATA.md). Every real call site
            omits it, so `created_at` keeps its normal DB-generated
            `now()` value exactly as before this parameter existed.
    """
    try:
        payload = {
            "actor_id": actor_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "before": before,
            "after": after,
        }
        if created_at is not None:
            payload["created_at"] = created_at
        supabase.table("audit_log").insert(payload).execute()
    except Exception:
        logger.exception("Failed to write audit log entry for action=%s", action)


def list_recent_events(limit: int = 10) -> list[dict]:
    """Fetch the most recent audit log entries, newest first, with the
    acting staff member's name/role joined in (PostgREST resource
    embedding via the `audit_log.actor_id -> staff_profiles.user_id`
    foreign key — one query, no manual join). Used by the admin dashboard
    (`app/services/dashboard_service.py`).
    """
    response = (
        supabase.table("audit_log")
        .select("*, staff_profiles(name, role)")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data


def list_events_for_entities(entity_type: str, entity_ids: list[str]) -> list[dict]:
    """Every audit log entry for a specific set of entities (e.g. every
    status-change event across one customer's orders), newest first, with
    the acting staff member's name/role joined in the same way as
    `list_recent_events`.

    Used to build the Customers screen's timeline
    (`app/services/customer_service.py`) by reusing this same audit trail
    Orders' own timeline is designed to reuse — see
    docs/Bakery_Command_Center_UX_Product_Blueprint_v1.md §5, and
    docs/EPIC1_CUSTOMERS.md for how it's actually wired up.
    """
    if not entity_ids:
        return []

    response = (
        supabase.table("audit_log")
        .select("*, staff_profiles(name, role)")
        .eq("entity_type", entity_type)
        .in_("entity_id", entity_ids)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data
