from app.core.database import supabase


def get_active_templates(collection: str | None = None) -> list[dict]:
    query = supabase.table("cake_templates").select("*").eq("active", True)

    if collection:
        query = query.ilike("category", collection)

    response = query.order("category").order("name").execute()
    return response.data


def get_template_by_id(template_id: str) -> dict | None:
    response = (
        supabase.table("cake_templates")
        .select("*")
        .eq("id", template_id)
        .maybe_single()
        .execute()
    )
    return response.data if response is not None else None
