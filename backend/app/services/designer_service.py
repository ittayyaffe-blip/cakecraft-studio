from app.core.database import supabase
from app.services.template_service import get_template_by_id


def _get_active_options(table: str) -> list[dict]:
    response = (
        supabase.table(table)
        .select("*")
        .eq("active", True)
        .order("display_order")
        .execute()
    )
    return response.data


def get_designer_options() -> dict:
    return {
        "cake_sizes": _get_active_options("cake_sizes"),
        "flavors": _get_active_options("flavors"),
        "fillings": _get_active_options("fillings"),
        "frostings": _get_active_options("frostings"),
    }


def get_designer_initialization(template_id: str) -> dict | None:
    template = get_template_by_id(template_id)
    if template is None:
        return None

    return {
        "template": template,
        "options": get_designer_options(),
    }
