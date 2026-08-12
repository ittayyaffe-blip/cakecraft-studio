"""Request/response schemas for admin Catalog Management
(`app/api/routes/admin/catalog.py`) — Master_Blueprint_v1.md §17 Phase 5.

Extends the existing customer-facing schemas (`app.schemas.designer_options`,
`app.schemas.template`) rather than duplicating their fields from scratch —
same "admin variant adds fields via inheritance" convention
`admin_customer.AdminCustomerDetail(AdminCustomerSummary)` already uses.
The one field every admin variant here adds is `active`: the customer-facing
option schemas never needed it (those endpoints only ever return active
rows), but the admin catalog view must show inactive rows too, so the flag
itself has to be visible.
"""

from pydantic import BaseModel

from app.schemas.designer_options import CakeSizeResponse, DesignerOptionResponse
from app.schemas.template import CakeTemplateResponse


class AdminDesignerOptionResponse(DesignerOptionResponse):
    active: bool


class AdminCakeSizeResponse(CakeSizeResponse):
    active: bool


class AdminDesignerOptionsResponse(BaseModel):
    cake_sizes: list[AdminCakeSizeResponse]
    flavors: list[AdminDesignerOptionResponse]
    fillings: list[AdminDesignerOptionResponse]
    frostings: list[AdminDesignerOptionResponse]


class AdminCakeTemplateWithOptions(CakeTemplateResponse):
    customization_options: AdminDesignerOptionsResponse


class TemplateActiveUpdateRequest(BaseModel):
    """Body for `PATCH /admin/catalog/templates/{id}/active` — same shape
    convention as `admin_order.OrderStatusUpdateRequest` (one field, named
    for what it sets)."""

    active: bool


class TemplateUpdateRequest(BaseModel):
    """Body for `PATCH /admin/catalog/templates/{id}` — true PATCH
    semantics: every field is optional, and only a field actually present
    in the request is applied (see the route's use of `model_dump(
    exclude_unset=True)`) — an omitted field leaves the stored value
    untouched, while `preview_image: null` explicitly clears it (`str |
    None` distinguishes "clear it" from "not mentioned" only in
    combination with exclude_unset; the type alone can't).

    `active` is deliberately not a field here — it stays Slice 2's own
    dedicated `PATCH .../active` endpoint, not folded into general edits.
    No validators here: this project's existing convention (see
    order_service.update_order_status) validates in the service layer,
    raising ValueError for a clean 400 — kept consistent rather than
    introducing Pydantic-level validation as a new pattern.
    """

    name: str | None = None
    category: str | None = None
    style: str | None = None
    base_price: float | None = None
    preview_image: str | None = None
