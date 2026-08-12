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


def _validate_and_clean(fields: dict) -> dict:
    """Shared value-validation for update_template and create_template:
    a blank name/category/style (whichever of the three is present in
    `fields`) is rejected, and trimmed when valid; a present base_price
    is rejected if negative (mirroring the `cake_templates.base_price >=
    0` check constraint from the initial schema migration). Applies only
    to whichever of these keys `fields` actually contains -- update_
    template may see any subset, create_template always sees all four
    (enforced upstream by TemplateCreateRequest's required fields, so
    there's nothing to check for their *presence* here, only their
    values). Never touches `active`/`bakery_id`/`id`/`created_at` --
    those never appear in `fields` in the first place, since neither
    caller's request schema declares them.

    Raises ValueError with a message naming the offending field, for a
    clean 400 at the route -- same "service validates, route maps
    ValueError to 400" shape order_service.update_order_status already
    established.
    """
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

    return cleaned


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
    untouched in the database. Mirrors order_service.update_order_status's
    shape: validate first (via _validate_and_clean) for a clean
    ValueError -> 400, then a single update, then re-fetched through the
    existing lookup rather than trusting the update call's own response.
    Assumes the template's existence has already been confirmed by the
    caller, same assumption set_template_active makes.

    Raises ValueError if `fields` is empty (nothing to do -- the caller
    should reject this before it gets here in the common case, but this
    function doesn't trust that), or via _validate_and_clean for an
    invalid supplied value.
    """
    if not fields:
        raise ValueError("No fields to update")

    cleaned = _validate_and_clean(fields)

    supabase.table("cake_templates").update(cleaned).eq("id", template_id).execute()
    return get_template_by_id(template_id)


def _get_bakery_id() -> str:
    """The one seeded bakery row's id (supabase/migrations/20260729130000_
    seed_bakery.sql -- this is a single-tenant system, "no second
    location" per knowledge_base/business_information.md). Resolved here,
    never accepted from a client, so create_template can't be pointed at
    an arbitrary or wrong bakery.
    """
    response = supabase.table("bakery").select("id").limit(1).execute()
    return response.data[0]["id"]


def create_template(fields: dict) -> dict:
    """Create a new cake template and return the refreshed row.

    `fields` must already contain name/category/style/base_price --
    TemplateCreateRequest declares all four required, so FastAPI rejects
    a request missing any of them with 422 before this is ever called --
    plus optionally preview_image. `active` is never accepted here; the
    database's own `default true` applies, matching set_template_active's
    exclusive ownership of that flag elsewhere. `bakery_id` is resolved
    internally via _get_bakery_id, never from the caller.

    Mirrors update_template's shape: validate via the same shared
    _validate_and_clean helper for a clean ValueError -> 400 *before*
    touching the database at all (including the bakery lookup), then a
    single insert, then re-fetched through the existing lookup rather
    than trusting the insert call's own response.
    """
    cleaned = _validate_and_clean(fields)

    payload = {**cleaned, "bakery_id": _get_bakery_id()}
    response = supabase.table("cake_templates").insert(payload).execute()
    return get_template_by_id(response.data[0]["id"])
