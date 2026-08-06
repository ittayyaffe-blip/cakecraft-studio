"""Response schemas for the admin dashboard (`app/api/routes/admin/dashboard.py`).

`RecentAuditEvent`'s `staff_profiles` field name matches the PostgREST
embedded-resource key returned by `audit_service.list_recent_events`, same
convention as `app/schemas/admin_order.py`.
"""

from datetime import datetime

from pydantic import BaseModel

from app.schemas.admin_order import AdminOrderSummary


class AuditActor(BaseModel):
    name: str | None = None
    role: str | None = None


class RecentAuditEvent(BaseModel):
    id: str
    action: str
    entity_type: str
    entity_id: str | None = None
    created_at: datetime
    staff_profiles: AuditActor | None = None


class ServiceHealth(BaseModel):
    status: str


class DatabaseHealth(BaseModel):
    status: str
    latencyMs: float | None = None


class RailwayHealth(BaseModel):
    status: str
    environment: str | None = None
    serviceName: str | None = None


class NetlifyHealth(BaseModel):
    status: str
    note: str | None = None


class LastDeployment(BaseModel):
    commitSha: str | None = None
    deploymentId: str | None = None


class SystemHealth(BaseModel):
    backend: ServiceHealth
    database: DatabaseHealth
    railway: RailwayHealth
    netlify: NetlifyHealth
    lastDeployment: LastDeployment


class DashboardResponse(BaseModel):
    totalOrders: int
    todaysOrders: int
    ordersByStatus: dict[str, int]
    recentOrders: list[AdminOrderSummary]
    recentAuditEvents: list[RecentAuditEvent]
    systemHealth: SystemHealth
