import uuid

from pydantic import BaseModel

from app.schemas.template import CakeTemplateResponse


class DesignerOptionResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_order: int


class CakeSizeResponse(DesignerOptionResponse):
    price_adjustment: int
    servings_min: int | None
    servings_max: int | None


class DesignerOptionsResponse(BaseModel):
    cake_sizes: list[CakeSizeResponse]
    flavors: list[DesignerOptionResponse]
    fillings: list[DesignerOptionResponse]
    frostings: list[DesignerOptionResponse]


class DesignerInitResponse(BaseModel):
    template: CakeTemplateResponse
    options: DesignerOptionsResponse
