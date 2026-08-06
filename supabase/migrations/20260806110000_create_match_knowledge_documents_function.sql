-- CakeCraft Studio - Business Intelligence Layer: Bakery Knowledge RAG
--
-- match_knowledge_documents is the actual pgvector usage
-- knowledge_documents (previous migration) exists to support: given a
-- query embedding, return the top matches ordered by cosine distance
-- (`<=>`, pgvector's cosine-distance operator) computed natively in
-- Postgres rather than pulled into Python — the point of using pgvector
-- at all, not just storing vectors in a column. Called via
-- `supabase.rpc("match_knowledge_documents", {...})` from
-- rag_service.py. security definer + a fixed search_path so it runs
-- with the function owner's privileges regardless of caller, matching
-- how every other RPC-free query already runs under the backend's
-- service-role key.

create or replace function public.match_knowledge_documents(
  query_embedding vector(384),
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
