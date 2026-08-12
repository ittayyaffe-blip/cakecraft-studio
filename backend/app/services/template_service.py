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


# --- Admin Catalog Management (Master_Blueprint_v1.md §17 Phase 5) ---------
# Read-only foundation slice: every template, active and inactive, each
# paired with the full customization-options catalog. Deliberately
# independent of get_active_templates/designer_service._get_active_options
# above -- both filter to active=True for the customer-facing flows they
# serve, and must keep doing exactly that; the admin catalog view needs
# the opposite (everything, so staff can see what's hidden from customers
# and eventually reactivate it), so this queries directly rather than
# reusing an active-only helper.

_OPTION_TABLES = ("cake_sizes", "flavors", "fillings", "frostings")


def _get_all_options(table: str) -> list[dict]:
    response = supabase.table(table).select("*").order("display_order").execute()
    return response.data


def get_all_templates_with_options() -> list[dict]:
    """Every cake template (active and inactive) with the full
    customization-options catalog nested under each as
    `customization_options: {cake_sizes, flavors, fillings, frostings}`.

    Options are global, not per-template -- cake_sizes/flavors/fillings/
    frostings have no `template_id` (see supabase/migrations/20260731100000_
    create_designer_options.sql): any size/flavor/filling/frosting can be
    paired with any template today, the same relationship
    designer_service.get_designer_initialization already relies on
    (one template + the one shared options set). So every template in this
    response gets the identical options object -- computed once, not
    re-queried per template -- rather than a template-specific subset that
    doesn't exist in the schema.
    """
    templates = supabase.table("cake_templates").select("*").order("category").order("name").execute().data

    options = {table: _get_all_options(table) for table in _OPTION_TABLES}

    return [{**template, "customization_options": options} for template in templates]
