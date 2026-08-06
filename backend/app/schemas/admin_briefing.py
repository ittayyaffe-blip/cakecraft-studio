"""Response schema for the AI Daily Briefing
(`app/api/routes/admin/briefing.py`) — Final AI Intelligence Phase.
Composed by `briefing_service.get_daily_briefing()`.

`pendingNotifications.items` reuses `admin_notification.py`'s
`AdminNotification` directly — same PostgREST embed shape
`notification_service.list_notifications` already returns, no reason to
duplicate it.
"""

from datetime import datetime

from pydantic import BaseModel

from app.schemas.admin_notification import AdminNotification


class ForecastResult(BaseModel):
    date: str
    weekday: str
    predictedOrders: int
    predictedRevenue: float
    workloadLevel: str
    confidence: int
    reason: str
    confirmedOrdersForTomorrow: int
    historicalSampleSize: int


class HighPriorityOrder(BaseModel):
    id: str
    customerName: str | None = None
    templateName: str | None = None
    status: str
    reason: str


class PendingNotificationsSummary(BaseModel):
    total: int
    items: list[AdminNotification]


class DailyBriefing(BaseModel):
    todaysOrders: int
    todaysRevenue: float
    forecast: ForecastResult
    pendingNotifications: PendingNotificationsSummary
    highPriorityOrders: list[HighPriorityOrder]
    recommendedActions: list[str]
    generatedAt: datetime
