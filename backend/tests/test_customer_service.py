"""Dependency-free self-check for the pure logic in
`app.services.customer_service` and `app.services.search_utils` — no
network/DB required. Run from `backend/`:

    python -m tests.test_customer_service

The functions that actually call Supabase (list_customers,
get_customer_detail, get_customer_timeline, ...) are exercised live via
`fastapi.testclient.TestClient` instead — see docs/EPIC1_CUSTOMERS.md.
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.services import customer_service
from app.services.customer_service import (
    _get_order_stats_for_customers,
    _page_to_range,
    find_customer_by_email,
    find_customer_by_phone,
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


# --- find_customer_by_email / find_customer_by_phone (Step 3) --------------
# Mocked at the supabase boundary — the real query-shape/matching logic
# runs for real against fixed inputs, matching the pattern established in
# test_agent_service.py / test_notification_service.py.


def test_find_customer_by_email_known_customer():
    fake_customer = {"id": "cust-1", "name": "Jane Doe", "email": "jane@example.com"}
    with patch.object(customer_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            SimpleNamespace(data=[fake_customer])
        )
        customer, is_ambiguous = find_customer_by_email("jane@example.com")
    assert customer == fake_customer
    assert is_ambiguous is False


def test_find_customer_by_email_unknown_customer():
    with patch.object(customer_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            SimpleNamespace(data=[])
        )
        customer, is_ambiguous = find_customer_by_email("stranger@example.com")
    assert customer is None
    assert is_ambiguous is False


def test_find_customer_by_email_ambiguous_match_does_not_guess():
    duplicates = [
        {"id": "cust-1", "name": "Jane Doe", "email": "shared@example.com"},
        {"id": "cust-2", "name": "Jane D.", "email": "shared@example.com"},
    ]
    with patch.object(customer_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            SimpleNamespace(data=duplicates)
        )
        customer, is_ambiguous = find_customer_by_email("shared@example.com")
    assert customer is None
    assert is_ambiguous is True


def test_find_customer_by_phone_matches_normalized_digits():
    fake_customer = {"id": "cust-1", "name": "Jane Doe", "phone": "+33 6 12 34 56 78"}
    with patch.object(customer_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value.select.return_value.execute.return_value = (
            SimpleNamespace(data=[fake_customer])
        )
        # Inbound WhatsApp delivers digits-only; the stored record is
        # formatted with spaces/punctuation -- normalization must bridge them.
        customer, is_ambiguous = find_customer_by_phone("33612345678")
    assert customer == fake_customer
    assert is_ambiguous is False


def test_find_customer_by_phone_unknown_number():
    with patch.object(customer_service, "supabase") as mock_supabase:
        mock_supabase.table.return_value.select.return_value.execute.return_value = (
            SimpleNamespace(data=[])
        )
        customer, is_ambiguous = find_customer_by_phone("33699999999")
    assert customer is None
    assert is_ambiguous is False


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
