"""RAG (Retrieval-Augmented Generation) service — Business Intelligence
Layer, "Bakery Knowledge RAG". See docs/BUSINESS_INTELLIGENCE_LAYER.md
"RAG Design" for the full write-up.

Retrieval: a fitted TF-IDF vectorizer (persisted by
tools/ingest_knowledge_base.py to backend/app/rag_models/) embeds the
query with the exact same vocabulary/weights used at ingestion time,
then `match_knowledge_documents` (a pgvector cosine-distance RPC —
see the migration) returns the most relevant chunks from
`knowledge_documents`, computed natively in Postgres.

Generation: the retrieved chunks are handed to Claude as the *only*
source of bakery-specific facts, with an explicit instruction to answer
from them and say so plainly when they don't cover the question — this
is what makes it RAG rather than an ungrounded chatbot: the model
answers from *retrieved* documents, not its own general knowledge of
what a bakery might do.

Gracefully degrades, same contract as the Communication Adapters: no
ANTHROPIC_API_KEY configured means `is_configured()` is False and
answer_question() returns the raw retrieved excerpts without an LLM-
synthesized answer, rather than raising.
"""

import logging
from pathlib import Path

import anthropic
import joblib
import numpy as np

from app.core.config import settings
from app.core.database import supabase

logger = logging.getLogger(__name__)

# The knowledge base's natural TF-IDF vocabulary (~900 terms across
# knowledge_base/*.md) is padded to this fixed width to match
# knowledge_documents.embedding's pgvector column — see
# tools/ingest_knowledge_base.py and the migration that widened it.
EMBEDDING_DIMENSIONS = 1024

_VECTORIZER_PATH = Path(__file__).resolve().parent.parent / "rag_models" / "tfidf_vectorizer.joblib"
_MODEL = "claude-sonnet-5"

_vectorizer_cache = None


def _load_vectorizer():
    """Cached at module level — the fitted vectorizer is small (persisted
    once by the ingestion script) and never changes between requests, so
    there's no reason to reload it from disk on every query.
    """
    global _vectorizer_cache
    if _vectorizer_cache is None:
        _vectorizer_cache = joblib.load(_VECTORIZER_PATH)
    return _vectorizer_cache


def embed_texts(vectorizer, texts: list[str]) -> np.ndarray:
    """TF-IDF-vectorize texts with the given fitted vectorizer, then
    zero-pad to EMBEDDING_DIMENSIONS. A vectorizer's own output width
    equals its vocabulary size, which can be smaller than the fixed
    pgvector column width (`max_features` is a ceiling, not a
    guarantee) — caught live during ingestion (see the migration that
    widened the column after this exact mismatch broke retrieval).

    Used identically at ingestion time (tools/ingest_knowledge_base.py
    imports this function directly) and query time (below) so both
    produce directly-comparable, same-width vectors — the single most
    important correctness property of this retrieval pipeline. Never
    reimplement this padding logic a second time.
    """
    vectors = vectorizer.transform(texts).toarray()
    if vectors.shape[1] < EMBEDDING_DIMENSIONS:
        pad_width = EMBEDDING_DIMENSIONS - vectors.shape[1]
        vectors = np.pad(vectors, ((0, 0), (0, pad_width)))
    return vectors


def is_configured() -> bool:
    return bool(settings.anthropic_api_key)


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """The most relevant knowledge base chunks for a query, via the
    pgvector cosine-distance RPC. Returns [] if the knowledge base
    hasn't been ingested yet (an empty table, not an error).
    """
    vectorizer = _load_vectorizer()
    query_vector = embed_texts(vectorizer, [query])[0].tolist()
    response = supabase.rpc(
        "match_knowledge_documents", {"query_embedding": query_vector, "match_count": top_k}
    ).execute()
    return response.data


def _build_prompt(question: str, chunks: list[dict]) -> str:
    context = "\n\n---\n\n".join(f"[{c['title']}]\n{c['content']}" for c in chunks)
    return (
        "You are answering a bakery staff member's operational question using ONLY the "
        "bakery documents below. If the documents don't cover the question, say so plainly "
        "instead of guessing. Be concise and concrete — this is an internal operations tool, "
        "not a customer-facing chat.\n\n"
        f"BAKERY DOCUMENTS:\n{context}\n\n"
        f"QUESTION: {question}"
    )


def answer_question(question: str, top_k: int = 5) -> dict:
    """Retrieve + generate: the actual RAG pipeline. Always returns the
    retrieved sources (so staff can see what grounded the answer, or
    read the excerpts directly if generation isn't configured) plus an
    `answer` field — either a Claude-synthesized answer, or a clear
    "not configured" message that still surfaces the raw excerpts.
    """
    chunks = retrieve(question, top_k=top_k)
    sources = [{"title": c["title"], "sourceFile": c["source_file"], "similarity": round(c["similarity"], 3)} for c in chunks]

    if not chunks:
        return {"answer": "No relevant information found in the bakery knowledge base.", "sources": []}

    if not is_configured():
        excerpt = "\n\n".join(f"From {c['title']}: {c['content']}" for c in chunks[:2])
        return {
            "answer": f"AI answer generation is not configured. Closest matching excerpts:\n\n{excerpt}",
            "sources": sources,
        }

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        # thinking disabled: see agent_service._claude's docstring
        # comment — extended thinking otherwise consumes the token
        # budget with no benefit for this kind of grounded-synthesis task.
        response = client.messages.create(
            model=_MODEL,
            max_tokens=500,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": _build_prompt(question, chunks)}],
        )
        answer = next(block.text for block in response.content if block.type == "text")
    except Exception:
        logger.exception("RAG answer generation failed for question: %s", question)
        answer = "AI answer generation failed. See the retrieved sources below for the relevant policy excerpts."

    return {"answer": answer, "sources": sources}
