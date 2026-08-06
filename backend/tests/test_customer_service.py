"""Dependency-free self-check for the pure logic in
`app.services.customer_service` and `app.services.search_utils` — no
network/DB required. Run from `backend/`:

    python -m tests.test_customer_service

The functions that actually call Supabase (list_customers,
get_customer_detail, get_customer_timeline, ...) are exercised live via
`fastapi.testclient.TestClient` instead — see docs/EPIC1_CUSTOMERS.md.
"""

from app.services.customer_service import (
    _get_order_stats_for_customers,
    _page_to_range,
    get_customer_ai_insights,
    get_customer_communications,
)
from app.services.search_utils import sanitize_search_term


def test_page_to_range_matches_order_service_convention():
    assert _page_to_range(page=1, page_size=20) == (0, 19)
    assert _page_to_range(page=3, page_size=10) == (20, 29)


def test_sanitize_search_term_strips_or_filter_delimiters():
    assert sanitize_search_term("O'Brien, John (VIP)") == "O'Brien  John  VIP"


def test_sanitize_search_term_handles_plain_input():
    assert sanitize_search_term("  jane doe  ") == "jane doe"


def test_get_order_stats_for_customers_empty_input_short_circuits():
    # No network call should happen for an empty id list.
    assert _get_order_stats_for_customers([]) == {}


def test_communications_placeholder_shape():
    result = get_customer_communications("irrelevant-id")
    assert result == {"enabled": False, "items": []}


def test_ai_insights_placeholder_shape():
    result = get_customer_ai_insights("irrelevant-id")
    assert result == {"enabled": False, "insights": []}


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
