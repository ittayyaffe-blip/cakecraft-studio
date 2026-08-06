"""Request/response schemas for the Bakery Knowledge RAG endpoint
(`app/api/routes/admin/rag.py`) — Business Intelligence Layer.
"""

from pydantic import BaseModel


class RagAskRequest(BaseModel):
    question: str


class RagSource(BaseModel):
    title: str
    sourceFile: str
    similarity: float


class RagAskResponse(BaseModel):
    answer: str
    sources: list[RagSource]
