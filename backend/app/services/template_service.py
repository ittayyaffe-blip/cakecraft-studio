from app.core.database import supabase


def get_active_templates() -> list[dict]:
    response = (
        supabase.table("cake_templates")
        .select("*")
        .eq("active", True)
        .order("category")
        .order("name")
        .execute()
    )
    return response.data
