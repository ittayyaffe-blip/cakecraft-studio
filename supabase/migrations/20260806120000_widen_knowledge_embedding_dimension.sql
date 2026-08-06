-- CakeCraft Studio - Business Intelligence Layer: Bakery Knowledge RAG
--
-- Caught live: the knowledge base's natural TF-IDF vocabulary (888
-- terms across knowledge_base/*.md) is more than double the original
-- vector(384) column width, so max_features=384 was silently dropping
-- specific, low-frequency-but-important terms in favor of common ones
-- — "deposit"/"deposits" among them, which broke retrieval for a real
-- "wedding cake deposit" query even though both the Pricing Policy and
-- Wedding Cake Guide state that policy explicitly. Widened to 1024,
-- comfortably above the current 888-term vocabulary with room for the
-- knowledge base to grow before this needs revisiting again.
--
-- alter column ... type requires an explicit cast, and the column is
-- not null — the old 384-dim vectors are meaningless at the new width
-- and tools/ingest_knowledge_base.py re-ingests everything immediately
-- after this migration anyway, so the existing rows are cleared first
-- rather than cast in place.

delete from public.knowledge_documents;

alter table public.knowledge_documents
  alter column embedding type vector(1024);

create or replace function public.match_knowledge_documents(
  query_embedding vector(1024),
  match_count int default 5
)
returns table (
  id uuid,
  title text,
  source_file text,
  content text,
  similarity float
)
language sql
stable
security definer
set search_path = public
as $$
  select
    id,
    title,
    source_file,
    content,
    1 - (embedding <=> query_embedding) as similarity
  from public.knowledge_documents
  order by embedding <=> query_embedding
  limit match_count;
$$;
