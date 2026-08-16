"""Dependency-free self-check for app.services.serving_band_service --
pure Python, no network/DB/Anthropic call anywhere (there is nothing to
mock: compute_serving_band()/is_standard_ordering_eligible() take a
plain int and return a plain value). Run from `backend/`:

    python -m tests.test_serving_band_service
"""

from app.services.serving_band_service import (
    CUSTOM_EVENT,
    compute_serving_band,
    is_standard_ordering_eligible,
)


def test_10_guests_is_small():
    assert compute_serving_band(10) == "SMALL"


def test_12_guests_is_small():
    assert compute_serving_band(12) == "SMALL"


def test_13_guests_is_medium():
    assert compute_serving_band(13) == "MEDIUM"


def test_20_guests_is_medium():
    assert compute_serving_band(20) == "MEDIUM"


def test_21_guests_is_large():
    assert compute_serving_band(21) == "LARGE"


def test_30_guests_is_large():
    assert compute_serving_band(30) == "LARGE"


def test_31_guests_is_xl():
    assert compute_serving_band(31) == "XL"


def test_50_guests_is_xl():
    assert compute_serving_band(50) == "XL"


def test_51_guests_is_event():
    assert compute_serving_band(51) == "EVENT"


def test_75_guests_is_event():
    assert compute_serving_band(75) == "EVENT"


def test_76_guests_is_custom_event():
    assert compute_serving_band(76) == CUSTOM_EVENT


def test_100_guests_is_custom_event():
    assert compute_serving_band(100) == CUSTOM_EVENT


def test_a_small_guest_count_below_the_stated_floor_still_maps_to_small():
    # No enforced minimum existed before this feature (any customer could
    # already order "Small" regardless of stated guest count) -- preserved
    # per the explicit instruction, rather than newly rejecting a
    # genuinely small celebration.
    assert compute_serving_band(1) == "SMALL"
    assert compute_serving_band(4) == "SMALL"


def test_zero_and_negative_guest_counts_are_rejected():
    for bad in (0, -1, -100):
        try:
            compute_serving_band(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for guest_count={bad}")


def test_non_integer_guest_counts_are_rejected():
    for bad in (3.5, "20", None, True, False):
        try:
            compute_serving_band(bad)
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError(f"expected an error for guest_count={bad!r}")


def test_is_standard_ordering_eligible_true_up_to_75():
    for count in (1, 12, 13, 30, 31, 75):
        assert is_standard_ordering_eligible(count) is True


def test_is_standard_ordering_eligible_false_for_76_plus():
    assert is_standard_ordering_eligible(76) is False
    assert is_standard_ordering_eligible(100) is False


def test_is_standard_ordering_eligible_false_for_invalid_input_never_raises():
    # The one authoritative gate must be safe to call with untrusted
    # input directly (e.g. straight off a request) without the caller
    # needing its own try/except.
    for bad in (0, -5, "not a number", None):
        assert is_standard_ordering_eligible(bad) is False


def run_all() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} checks passed.")


if __name__ == "__main__":
    run_all()
