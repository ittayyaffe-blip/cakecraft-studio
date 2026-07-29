import uuid

from pydantic import BaseModel


class CollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    image: str | None
    display_order: int
