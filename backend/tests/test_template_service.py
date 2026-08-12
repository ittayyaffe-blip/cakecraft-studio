"""Dependency-free self-check for `app.services.template_service` -- no
live Supabase connection required. Run from `backend/`:

    python -m tests.test_template_service

`supabase` is mocked at the module boundary (same convention every other
test module in this project uses) with one chainable MagicMock per table
name, so each table's `.execute()` returns its own fixed data regardless
of call order.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import template_service


def _chainable(data):
    """A `supabase.table(...)` stand-in: every query-builder method
    (`select`/`eq`/`ilike`/`order`) returns itself so calls chain freely,
    however many are used for a given query, and `.execute()` always
    yields `data` -- matching the real `postgrest` client's builder shape.
    """
    m = MagicMock()
    m.select.return_value = m
    m.eq.return_value = m
    m.ilike.return_value = m
    m.order.return_value = m
    m.maybe_single.return_value = m
    m.execute.return_value = SimpleNamespace(data=data)
    return m


def _mock_supabase(tables: dict) -> MagicMock:
    mock = MagicMock()
    mock.table.side_effect = lambda name: tables[name]
    return mock


# --- get_active_templates: existing customer-facing behavior, unchanged ----
# (Phase 5's read-only admin slice adds a new function below; it must not
# change this one -- see template_service.py's own comment on why the two
# stay independent.)


def test_get_active_templates_filters_to_active_only():
    templates_table = _chainable([{"id": "t1", "name": "Ivory Classic", "active": True}])
    with patch.object(template_service, "supabase", _mock_supabase({"cake_templates": templates_table})):
        result = template_service.get_active_templates()

    assert result == [{"id": "t1", "name": "Ivory Classic", "active": True}]
    templates_table.eq.assert_called_once_with("active", True)
    templates_table.ilike.assert_not_called()


def test_get_active_templates_filters_by_collection_when_given():
    templates_table = _chainable([{"id": "t1", "name": "Wedding Cake", "category": "Wedding"}])
    with patch.object(template_service, "supabase", _mock_supabase({"cake_templates": templates_table})):
        template_service.get_active_templates(collection="Wedding")

    templates_table.ilike.assert_called_once_with("category", "Wedding")


# --- get_all_templates_with_options: the new admin Catalog Management read -


def test_get_all_templates_with_options_includes_active_and_inactive_templates():
    templates_table = _chainable(
        [
            {"id": "t1", "name": "Ivory Classic", "category": "Wedding", "active": True},
            {"id": "t2", "name": "Retired Design", "category": "Birthday", "active": False},
        ]
    )
    tables = {
        "cake_templates": templates_table,
        "cake_sizes": _chainable([]),
        "flavors": _chainable([]),
        "fillings": _chainable([]),
        "frostings": _chainable([]),
    }
    with patch.object(template_service, "supabase", _mock_supabase(tables)):
        result = template_service.get_all_templates_with_options()

    assert len(result) == 2
    assert {t["id"] for t in result} == {"t1", "t2"}
    assert any(t["active"] is False for t in result)  # the inactive one is not filtered out
    templates_table.eq.assert_not_called()  # unlike get_active_templates, no active=True filter


def test_get_all_templates_with_options_nests_the_full_options_catalog_under_each_template():
    # Options have no template_id (see the migration) -- every template
    # gets the identical, unfiltered options set, active and inactive rows
    # both included.
    templates_table = _chainable([{"id": "t1", "name": "A"}, {"id": "t2", "name": "B"}])
    cake_sizes = [{"id": "s1", "name": "Small", "active": True, "display_order": 1, "price_adjustment": 0}]
    flavors = [
        {"id": "f1", "name": "Vanilla", "active": True, "display_order": 1},
        {"id": "f2", "name": "Discontinued Flavor", "active": False, "display_order": 2},
    ]
    tables = {
        "cake_templates": templates_table,
        "cake_sizes": _chainable(cake_sizes),
        "flavors": _chainable(flavors),
        "fillings": _chainable([]),
        "frostings": _chainable([]),
    }
    with patch.object(template_service, "supabase", _mock_supabase(tables)):
        result = template_service.get_all_templates_with_options()

    for template in result:
        assert template["customization_options"]["cake_sizes"] == cake_sizes
        assert template["customization_options"]["flavors"] == flavors
    # Both templates see the exact same options object -- confirms it was
    # computed once, not re-queried/re-filtered per template.
    assert result[0]["customization_options"] is result[1]["customization_options"]
    # Inactive option row is present, not filtered out (admin-only behavior).
    assert any(f["active"] is False for f in result[0]["customization_options"]["flavors"])


def test_get_all_templates_with_options_queries_all_four_option_tables_unordered_by_active():
    tables = {
        "cake_templates": _chainable([]),
        "cake_sizes": _chainable([]),
        "flavors": _chainable([]),
        "fillings": _chainable([]),
        "frostings": _chainable([]),
    }
    with patch.object(template_service, "supabase", _mock_supabase(tables)):
        template_service.get_all_templates_with_options()

    for name in ("cake_sizes", "flavors", "fillings", "frostings"):
        tables[name].eq.assert_not_called()  # no active=True filter -- admin sees everything
        tables[name].order.assert_called_once_with("display_order")


# --- set_template_active: Catalog Management Slice 2 -----------------------


def test_set_template_active_updates_only_the_active_column_and_returns_the_refreshed_row():
    refreshed = {"id": "t1", "name": "Ivory Classic", "active": False}
    templates_table = _chainable(refreshed)
    with patch.object(template_service, "supabase", _mock_supabase({"cake_templates": templates_table})):
        result = template_service.set_template_active("t1", False)

    assert result == refreshed
    templates_table.update.assert_called_once_with({"active": False})
    templates_table.update.return_value.eq.assert_called_once_with("id", "t1")
    # Re-fetched through the existing lookup rather than trusting the
    # update call's own response -- same shape as update_order_status.
    templates_table.select.assert_called_once_with("*")
    templates_table.eq.assert_called_once_with("id", "t1")


def test_set_template_active_can_reactivate():
    refreshed = {"id": "t1", "name": "Ivory Classic", "active": True}
    templates_table = _chainable(refreshed)
    with patch.object(template_service, "supabase", _mock_supabase({"cake_templates": templates_table})):
        result = template_service.set_template_active("t1", True)

    assert result["active"] is True
    templates_table.update.assert_called_once_with({"active": True})


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
