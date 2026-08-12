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


def set_template_active(template_id: str, active: bool) -> dict:
    """Update a template's `active` flag and return the refreshed row.

    Mirrors order_service.update_order_status's shape exactly: a single-
    column `supabase` update, then re-fetched through the existing lookup
    rather than trusting the update call's own response. Assumes the
    template's existence has already been confirmed by the caller (see
    app/api/routes/admin/catalog.py, which needs the *previous* `active`
    value for the audit log entry anyway, so it already fetches the
    template first — same assumption update_order_status makes about the
    order it's updating).
    """
    supabase.table("cake_templates").update({"active": active}).eq("id", template_id).execute()
    return get_template_by_id(template_id)


def update_template(template_id: str, fields: dict) -> dict:
    """Partially update a template's editable identity fields -- name,
    category, style, base_price, preview_image. Never `active`; that
    stays set_template_active's own dedicated concern above, kept
    separate on purpose (see app/api/routes/admin/catalog.py). Nothing
    here can touch `active` or `bakery_id` even if asked to -- the only
    caller builds `fields` from TemplateUpdateRequest, whose schema
    doesn't declare either.

    `fields` should already be pre-filtered to only the keys the caller
    actually supplied (see the route's use of `body.model_dump(
    exclude_unset=True)`) -- true PATCH semantics, an omitted key is left
    untouched in the database. Validates the *values* of whatever keys
    are present, mirroring order_service.update_order_status's shape: a
    plain ValueError for a clean 400, checked before any `supabase` call,
    then a single update, then re-fetched through the existing lookup
    rather than trusting the update call's own response. Assumes the
    template's existence has already been confirmed by the caller, same
    assumption set_template_active makes.

    Raises ValueError if `fields` is empty (nothing to do -- the caller
    should reject this before it gets here in the common case, but this
    function doesn't trust that), or if a supplied name/category/style is
    blank, or a supplied base_price is negative (mirroring the `cake_
    templates.base_price >= 0` check constraint from the initial schema
    migration).
    """
    if not fields:
        raise ValueError("No fields to update")

    cleaned = dict(fields)

    for key in ("name", "category", "style"):
        if key in cleaned:
            value = cleaned[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must not be empty")
            cleaned[key] = value.strip()

    if "base_price" in cleaned:
        base_price = cleaned["base_price"]
        if base_price is None or base_price < 0:
            raise ValueError("base_price must be >= 0")

    supabase.table("cake_templates").update(cleaned).eq("id", template_id).execute()
    return get_template_by_id(template_id)
