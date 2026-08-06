"""Dashboard aggregation service for the admin Backoffice
(`app/api/routes/admin/dashboard.py`).

Composes read-only data across several existing domains — orders, the
audit log, and this process's own environment — that don't belong to any
one existing service. Nothing here writes anything.
"""

import logging
import os
import time
from datetime import datetime, timezone

from app.core.database import supabase
from app.services import order_service
from app.services.audit_service import list_recent_events

logger = logging.getLogger(__name__)

RECENT_ORDERS_LIMIT = 10
RECENT_AUDIT_EVENTS_LIMIT = 10


def _get_order_stats() -> dict:
    """Total orders, today's orders, and a count per status.

    One query, counted client-side: cheap at this project's order volume.
    If that ever stops being true, switch to a Postgres RPC that does the
    GROUP BY server-side instead of fetching every row.
    """
    response = supabase.table("orders").select("status, created_at").execute()
    rows = response.data

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    orders_by_status = {status: 0 for status in order_service.ORDER_STATUSES}
    todays_orders = 0

    for row in rows:
        if row["status"] in orders_by_status:
            orders_by_status[row["status"]] += 1
        if datetime.fromisoformat(row["created_at"]) >= today_start:
            todays_orders += 1

    return {
        "totalOrders": len(rows),
        "todaysOrders": todays_orders,
        "ordersByStatus": orders_by_status,
    }


def _get_system_health() -> dict:
    backend = {"status": "healthy"}

    db_start = time.perf_counter()
    try:
        supabase.table("bakery").select("id", count="exact", head=True).execute()
        database = {
            "status": "healthy",
            "latencyMs": round((time.perf_counter() - db_start) * 1000, 1),
        }
    except Exception:
        logger.exception("Dashboard database health check failed")
        database = {"status": "unreachable", "latencyMs": None}

    # Railway injects these into every deployed service's environment — no
    # Railway API call is made (that would need a separate API token this
    # project doesn't provision) and none is needed: reading our own
    # environment is a zero-credential way to confirm we're actually
    # running there and which deployment this is.
    railway_environment = os.environ.get("RAILWAY_ENVIRONMENT_NAME") or os.environ.get(
        "RAILWAY_ENVIRONMENT"
    )
    railway = (
        {
            "status": "running",
            "environment": railway_environment,
            "serviceName": os.environ.get("RAILWAY_SERVICE_NAME"),
        }
        if railway_environment
        else {"status": "unknown", "environment": None, "serviceName": None}
    )

    # The frontend is a standalone Railway service, not Netlify (see
    # docs/Project_Audit_Report_v1.md §5) — reported honestly rather than
    # showing a status for infrastructure that isn't actually in use.
    netlify = {
        "status": "not_configured",
        "note": "Frontend is served via Railway, not Netlify.",
    }

    last_deployment = {
        "commitSha": os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
        "deploymentId": os.environ.get("RAILWAY_DEPLOYMENT_ID"),
    }

    return {
        "backend": backend,
        "database": database,
        "railway": railway,
        "netlify": netlify,
        "lastDeployment": last_deployment,
    }


def get_dashboard_data() -> dict:
    stats = _get_order_stats()
    recent_orders = order_service.list_orders(page=1, page_size=RECENT_ORDERS_LIMIT)["items"]
    recent_audit_events = list_recent_events(limit=RECENT_AUDIT_EVENTS_LIMIT)

    return {
        **stats,
        "recentOrders": recent_orders,
        "recentAuditEvents": recent_audit_events,
        "systemHealth": _get_system_health(),
    }
