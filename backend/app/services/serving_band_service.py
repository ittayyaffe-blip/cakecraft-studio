"""Deterministic guest-count -> serving-band classification (Servings +
Event Pricing). Pure Python, no Claude/Anthropic dependency anywhere --
same "small, dedicated module for one cross-cutting deterministic
business rule" shape as priority_service.py (Pickup Date + Order
Priority). Claude never decides a serving band or a price; it may only
ever read this module's output.

Architecture: guest_count -> serving band -> size/price -- never the
reverse, and never a customer- or Claude-supplied override. Standard
online ordering covers 1-75 guests (SMALL through EVENT, see
compute_serving_band's own note on why SMALL's floor is lenient); 76+ is
CUSTOM_EVENT and can never be automatically priced or reach standard
checkout/payment -- see is_standard_ordering_eligible(), the one
authoritative gate every real order-creation path (Website route, Chat,
order_service.create_order itself) independently re-checks.
"""

# Ordered ascending by upper bound. The stated "typical serving count" for
# each band matches Maison de Gâteau's own approved figures exactly
# (SMALL 8-12, MEDIUM 13-20, LARGE 21-30, XL 31-50, EVENT 51-75) --
# chosen, not invented: this migration widened the three existing
# cake_sizes' own servings_min/max to these same numbers (see
# 20260816090000_add_xl_and_event_cake_sizes.sql), so this table and the
# database's own descriptive metadata always agree.
_SERVING_BANDS = (
    ("SMALL", 12),
    ("MEDIUM", 20),
    ("LARGE", 30),
    ("XL", 50),
    ("EVENT", 75),
)

CUSTOM_EVENT = "CUSTOM_EVENT"
_CUSTOM_EVENT_MIN_GUESTS = 76

# The exact cake_sizes.name value each standard band maps to -- reused by
# order_service.create_order() to look up the real DB row (id,
# price_adjustment) for pricing, and by the admin Back Office/Bakery
# Manager for display. Matches the name a manager already sees in the
# catalog/Designer options list.
BAND_TO_SIZE_NAME = {
    "SMALL": "Small",
    "MEDIUM": "Medium",
    "LARGE": "Large",
    "XL": "XL",
    "EVENT": "Event",
}

# The one approved customer-facing wording for 76+ -- used verbatim by
# the Website route, the admin-facing error, and Chat, so a customer
# gets the exact same message regardless of channel.
CUSTOM_EVENT_MESSAGE = (
    "For celebrations with more than 75 guests, our team will create a tailored cake "
    "and pricing proposal for your event. Please contact us directly and we'll be happy to help."
)


def compute_serving_band(guest_count: int) -> str:
    """Returns one of "SMALL"/"MEDIUM"/"LARGE"/"XL"/"EVENT"/"CUSTOM_EVENT".

    Raises ValueError for a non-positive/non-integer guest count -- the
    one thing this function refuses to guess about (same posture as
    order_service.validate_pickup_datetime's own malformed-input
    handling).

    A guest count below SMALL's own stated floor (8) still resolves to
    SMALL rather than being rejected: there was never an enforced
    minimum before this feature existed (any customer could already
    order "Small" regardless of how many guests they actually had), and
    the explicit instruction was to preserve that -- "a sensible minimum
    rather than breaking existing valid small orders" -- not to newly
    invalidate a genuinely small celebration.
    """
    if not isinstance(guest_count, int) or isinstance(guest_count, bool) or guest_count < 1:
        raise ValueError("Guest count must be a positive whole number.")

    if guest_count >= _CUSTOM_EVENT_MIN_GUESTS:
        return CUSTOM_EVENT

    for band, max_guests in _SERVING_BANDS:
        if guest_count <= max_guests:
            return band
    return CUSTOM_EVENT  # unreachable given the >=76 check above -- kept as a safe fallback, never guesses a standard band


def is_standard_ordering_eligible(guest_count) -> bool:
    """The one authoritative eligibility gate: standard automated
    checkout/payment is only for a guest count that resolves to a
    standard band (<=75), never CUSTOM_EVENT and never invalid input.
    Every real caller (the Website route, order_service.create_order,
    Chat) calls this fresh -- never trusts a frontend-computed band, so
    a direct POST cannot bypass the 75-guest rule.
    """
    try:
        return compute_serving_band(guest_count) != CUSTOM_EVENT
    except (ValueError, TypeError):
        return False
