"""Bakery Knowledge RAG route — Business Intelligence Layer.

One endpoint: ask a bakery operational question, get an answer grounded
in the retrieved knowledge_documents (see rag_service.py). Same auth
pattern as every other admin route. Read-only (retrieval + generation,
no writes), so nothing here touches the audit log — same posture as
dashboard.py/briefing.py.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_admin
from app.schemas.admin_rag import RagAskRequest, RagAskResponse
from app.services.auth_service import AdminIdentity
from app.services.rag_service import answer_question

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/rag", tags=["admin-rag"])


@router.post("/ask", response_model=RagAskResponse)
def ask(request: RagAskRequest, admin: AdminIdentity = Depends(get_current_admin)):
    try:
        return answer_question(request.question)
    except Exception:
        logger.exception("RAG ask failed for question: %s", request.question)
        raise HTTPException(status_code=500, detail="Failed to answer the question")
