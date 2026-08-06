-- CakeCraft Studio - Business Intelligence Layer: Bakery Knowledge RAG
--
-- knowledge_documents holds chunked bakery operational documents
-- (knowledge_base/*.md — Operations Manual, Recipe Guide, Allergen
-- Policy, Delivery/Pickup Policy, Wedding/Corporate guides, Customer
-- Service Handbook, Pricing Policy, Production Workflow, Decoration
-- Standards, Food Safety Procedures, FAQ) plus a TF-IDF embedding per
-- chunk, so rag_service.py can retrieve the most relevant passages for
-- a staff question and ground the AI Agent's answers in them instead of
-- the model's own unguided knowledge. See
-- docs/BUSINESS_INTELLIGENCE_LAYER.md "RAG Design".
--
-- Embeddings are 384-dimensional TF-IDF vectors (scikit-learn
-- TfidfVectorizer, max_features=384) fit once at ingestion time by
-- tools/ingest_knowledge_base.py — not a neural embedding model or API,
-- a deliberate choice matching this project's "capstone, not research"
-- framing: no new external embedding dependency, no API key/cost,
-- fully offline and reproducible for a ~13-document knowledge base
-- where query/document vocabulary genuinely overlaps (staff asking
-- about "wedding cake deposit" will use words that literally appear in
-- the Wedding Cake Guide and Pricing Policy).
--
-- No vector index (ivfflat/hnsw): at this document-collection scale
-- (a few dozen to ~150 chunks), a sequential scan with cosine-distance
-- ordering is effectively instant, and ivfflat indexes need enough rows
-- to train meaningful clusters — premature here. Add one if the
-- knowledge base grows into the thousands of chunks.

create extension if not exists vector;

create table if not exists public.knowledge_documents (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  source_file text not null,
  chunk_index int not null,
  content text not null,
  embedding vector(384) not null,
  created_at timestamptz not null default now()
);

create index if not exists knowledge_documents_source_file_idx
  on public.knowledge_documents (source_file);

-- Locked out of the Data API by default, matching every other table in
-- this project — the FastAPI backend's service-role key bypasses RLS.
alter table public.knowledge_documents enable row level security;
