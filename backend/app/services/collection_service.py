from app.core.database import supabase


def get_active_collections() -> list[dict]:
    response = (
        supabase.table("collections")
        .select("*")
        .eq("active", True)
        .order("display_order")
        .execute()
    )
    return response.data
