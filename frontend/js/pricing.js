// CakeCraft Studio — pricing engine. Pure functions only: given a
// designerState, compute a value and return it. No DOM access, no fetches.
// This is the one place pricing math is allowed to live — extend here
// (premium options, discounts, AI suggestions, etc.), never in the UI code.

function calculateCurrentPrice(designerState) {
  const basePrice = designerState.template ? designerState.template.base_price : 0;
  const sizeAdjustment = designerState.cakeSize ? designerState.cakeSize.price_adjustment : 0;

  return basePrice + sizeAdjustment;
}

function getServingRange(designerState) {
  if (!designerState.cakeSize) {
    return "Select a cake size";
  }

  const { servings_min, servings_max } = designerState.cakeSize;
  return `${servings_min}–${servings_max} servings`;
}

// Servings + Event Pricing. Mirrors backend/app/services/
// serving_band_service.py's own band table exactly -- duplicated here
// deliberately, same convention as customer-information.js's
// CATEGORY_MIN_LEAD_DAYS (presentation-only, no reason to round-trip the
// network for an immediate recommendation). Never authoritative: the
// backend independently derives the real size/price from guest_count on
// every order, ignoring whatever size this page's picker shows.
const SERVING_BANDS = [
  { band: "SMALL", maxGuests: 12, sizeName: "Small" },
  { band: "MEDIUM", maxGuests: 20, sizeName: "Medium" },
  { band: "LARGE", maxGuests: 30, sizeName: "Large" },
  { band: "XL", maxGuests: 50, sizeName: "XL" },
  { band: "EVENT", maxGuests: 75, sizeName: "Event" },
];

const CUSTOM_EVENT_GUEST_MINIMUM = 76;

const CUSTOM_EVENT_MESSAGE =
  "For celebrations with more than 75 guests, our team will create a tailored cake and pricing " +
  "proposal for your event. Please contact us directly and we'll be happy to help.";

// Returns { band, sizeName } for a standard guest count, or
// { band: "CUSTOM_EVENT" } for 76+. Guest counts below SMALL's own
// stated floor (8) still resolve to SMALL -- same "preserve existing
// valid small orders" reasoning as the backend's own compute_serving_band.
function getRecommendedBand(guestCount) {
  if (!Number.isInteger(guestCount) || guestCount < 1) {
    return null;
  }
  if (guestCount >= CUSTOM_EVENT_GUEST_MINIMUM) {
    return { band: "CUSTOM_EVENT", sizeName: null };
  }
  const match = SERVING_BANDS.find((entry) => guestCount <= entry.maxGuests);
  return match ? { band: match.band, sizeName: match.sizeName } : { band: "CUSTOM_EVENT", sizeName: null };
}
