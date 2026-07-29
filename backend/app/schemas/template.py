import uuid

from pydantic import BaseModel


class CakeTemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    style: str
    base_price: float
    preview_image: str | None
    active: bool
