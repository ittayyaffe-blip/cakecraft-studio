"""Tiny shared helper for building safe PostgREST `.or_()` search filters.

Used by every admin list endpoint that free-text searches across multiple
columns — `order_service.list_orders` (via a customer lookup) and
`customer_service.list_customers` — so the same escaping rule lives in
exactly one place instead of being copied per service.
"""


def sanitize_search_term(term: str) -> str:
    """Strip PostgREST's own or-filter delimiters (",", "(", ")") out of a
    user-supplied search term so it can't be misread as filter syntax.

    Not a security boundary — `supabase-py`'s query builder is parameterized,
    never raw SQL, so there is no injection risk either way. This only
    avoids a confusing 400 on a legitimate search that happens to contain
    one of these characters.
    """
    return term.replace(",", " ").replace("(", " ").replace(")", " ").strip()
