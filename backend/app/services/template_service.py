from app.core.database import supabase


def get_active_templates(collection: str | None = None) -> list[dict]:
    query = supabase.table("cake_templates").select("*").eq("active", True)

    if collection:
        query = query.ilike("category", collection)

    response = query.order("category").order("name").execute()
    return response.data
