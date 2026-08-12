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
