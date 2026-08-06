"""Dependency-free self-check for the pure logic in
`app.services.briefing_service` — no network/DB required. Run from
`backend/`:

    python -m tests.test_briefing_service

`get_daily_briefing`, `_todays_stats`, and `_high_priority_orders`
themselves touch Supabase and are exercised live via
`fastapi.testclient.TestClient` instead (GET /admin/briefing) — see
docs/FINAL_AI_INTELLIGENCE_PHASE.md. `_recommended_actions` is the one
piece of real branching logic that's pure, so it's what's covered here.
"""

from app.services.briefing_service import _recommended_actions

_MODERATE_FORECAST = {"workloadLevel": "Moderate", "predictedOrders": 5}
_HIGH_FORECAST = {"workloadLevel": "High", "predictedOrders": 20}


def test_no_actions_when_everything_is_quiet():
    actions = _recommended_actions(0, 0, _MODERATE_FORECAST)
    assert actions == ["No urgent items — a good day to get ahead on prep or outreach."]


def test_flags_pending_notifications():
    actions = _recommended_actions(3, 0, _MODERATE_FORECAST)
    assert any("3 notifications awaiting approval" in a for a in actions)


def test_pending_notification_singular_wording():
    actions = _recommended_actions(1, 0, _MODERATE_FORECAST)
    assert any("1 notification awaiting approval" in a for a in actions)


def test_flags_high_priority_orders():
    actions = _recommended_actions(0, 2, _MODERATE_FORECAST)
    assert any("2 high-priority order(s)" in a for a in actions)


def test_flags_high_workload_forecast():
    actions = _recommended_actions(0, 0, _HIGH_FORECAST)
    assert any("high-workload day" in a and "20 predicted orders" in a for a in actions)


def test_moderate_workload_does_not_trigger_staffing_action():
    actions = _recommended_actions(0, 0, _MODERATE_FORECAST)
    assert not any("workload day" in a for a in actions)


def test_multiple_conditions_all_surface():
    actions = _recommended_actions(2, 1, _HIGH_FORECAST)
    assert len(actions) == 3


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
