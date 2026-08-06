#!/usr/bin/env python
"""ONE-TIME (idempotent) ingestion of the bakery knowledge base
(`knowledge_base/*.md`) into `knowledge_documents` for RAG retrieval.

See docs/BUSINESS_INTELLIGENCE_LAYER.md "RAG Design" for the full
write-up. In one paragraph: each document is split into chunks along its
`## ` section headers, a single TF-IDF vectorizer is fit across every
chunk in the whole knowledge base (a shared vocabulary is what makes the
vectors comparable), each chunk's vector is stored alongside its text in
`knowledge_documents`, and the fitted vectorizer itself is persisted to
`backend/app/rag_models/tfidf_vectorizer.joblib` so query-time embedding
(rag_service.py) uses the exact same vocabulary/weights, not a
freshly-refit one.

Safe to re-run: existing rows are cleared before re-ingesting, so editing
a knowledge base document and re-running this script is the whole
update workflow — no separate "diff and patch" step.

Usage (from anywhere, run with the project's venv):
    <venv>/python tools/ingest_knowledge_base.py
"""

import sys
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import supabase  # noqa: E402
from app.services.rag_service import EMBEDDING_DIMENSIONS, embed_texts  # noqa: E402

KNOWLEDGE_BASE_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"
VECTORIZER_PATH = Path(__file__).resolve().parent.parent / "backend" / "app" / "rag_models" / "tfidf_vectorizer.joblib"


def _extract_title(markdown: str) -> str:
    first_line = markdown.strip().splitlines()[0]
    return first_line.lstrip("#").strip()


def _chunk_document(markdown: str) -> list[str]:
    """Split on `## ` section headers — each chunk is one section,
    header included, which keeps each chunk topically coherent and
    self-describing (a chunk about "Deposits" still says "Deposits" in
    its own text, useful both for retrieval and for the citation shown
    back to staff). The fragment before the first `## ` header (just the
    `# Title` line, since every document here opens straight into its
    first section) is dropped rather than kept as its own chunk — caught
    live: a bare title-only chunk is short enough that TF-IDF cosine
    similarity scores it unpredictably high against unrelated queries,
    and the title is already stored as its own column on every chunk, so
    indexing it a second time as "content" added noise, not signal.
    """
    lines = markdown.strip().splitlines()
    chunks: list[str] = []
    current: list[str] | None = None
    for line in lines:
        if line.startswith("## "):
            if current is not None:
                chunks.append("\n".join(current).strip())
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        chunks.append("\n".join(current).strip())
    return [c for c in chunks if c]


def load_chunks() -> list[dict]:
    """Every chunk from every knowledge base document, with its parent
    document's title and filename attached.
    """
    chunks = []
    for path in sorted(KNOWLEDGE_BASE_DIR.glob("*.md")):
        markdown = path.read_text(encoding="utf-8")
        title = _extract_title(markdown)
        for i, chunk_text in enumerate(_chunk_document(markdown)):
            chunks.append({"title": title, "source_file": path.name, "chunk_index": i, "content": chunk_text})
    return chunks


def delete_existing() -> None:
    existing = supabase.table("knowledge_documents").select("id").execute()
    ids = [row["id"] for row in existing.data]
    if ids:
        supabase.table("knowledge_documents").delete().in_("id", ids).execute()
        print(f"  Removed {len(ids)} previously-ingested chunks.")
    else:
        print("  No existing chunks found.")


def main() -> None:
    print("CakeCraft Studio — Knowledge Base Ingestion\n")

    print("Step 1/4: Loading and chunking knowledge_base/*.md...")
    chunks = load_chunks()
    print(f"  {len(chunks)} chunks from {len(set(c['source_file'] for c in chunks))} documents.")

    print("\nStep 2/4: Fitting the TF-IDF vectorizer across the whole corpus...")
    texts = [c["content"] for c in chunks]
    vectorizer = TfidfVectorizer(max_features=EMBEDDING_DIMENSIONS, stop_words="english")
    vectorizer.fit(texts)
    print(f"  Vocabulary size: {len(vectorizer.vocabulary_)} (target: {EMBEDDING_DIMENSIONS} dims).")

    # embed_texts (rag_service.py) is the exact same function query-time
    # retrieval calls on the persisted vectorizer — using it here too
    # (rather than a second, separate padding implementation) is what
    # guarantees ingestion-time and query-time vectors are directly
    # comparable. Caught live: an earlier version padded only here, not
    # at query time, and the two vector widths silently diverged.
    vectors = embed_texts(vectorizer, texts)

    print("\nStep 3/4: Removing previously-ingested chunks...")
    delete_existing()

    print("\nStep 4/4: Writing chunks + embeddings to knowledge_documents...")
    rows = [
        {
            "title": chunk["title"],
            "source_file": chunk["source_file"],
            "chunk_index": chunk["chunk_index"],
            "content": chunk["content"],
            "embedding": vectors[i].tolist(),
        }
        for i, chunk in enumerate(chunks)
    ]
    # Small enough to insert in one call; chunked defensively anyway in
    # case the knowledge base grows well past PostgREST's payload limits.
    batch_size = 50
    for start in range(0, len(rows), batch_size):
        supabase.table("knowledge_documents").insert(rows[start : start + batch_size]).execute()
    print(f"  Inserted {len(rows)} chunks.")

    VECTORIZER_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(vectorizer, VECTORIZER_PATH)
    print(f"\nFitted vectorizer saved to {VECTORIZER_PATH}")
    print("Done.")


if __name__ == "__main__":
    main()
