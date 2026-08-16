// CakeCraft Studio — order validation. Pure function only: given a
// designerState, determine whether the configuration is complete and
// return a plain object. No DOM, no fetches, no logging, no side effects.
// This is the one place validation rules are allowed to live — extend
// here (delivery date, inscription, decorations, etc.), never in the UI.

const REQUIRED_FIELDS = [
  { key: "template", label: "Cake Template" },
  { key: "cakeSize", label: "Cake Size" },
  { key: "flavor", label: "Flavor" },
  { key: "filling", label: "Filling" },
  { key: "frosting", label: "Frosting" },
];

// Servings + Event Pricing: guest count is required like every other
// field above, but a 76+ count is never just "missing" -- it's a
// distinct, permanent-for-this-session block (customEvent: true), never
// satisfied by picking a different size, and must never be silently
// treated as "valid" once a customer types a lower number back in (that
// part still works normally, since a fresh call to this function always
// re-derives the outcome fresh from whatever guestCount currently is).
function validateOrder(designerState) {
  const missing = REQUIRED_FIELDS.filter((field) => !designerState[field.key]).map(
    (field) => field.label
  );

  if (!designerState.guestCount) {
    missing.push("Number of Guests");
  }

  const recommended = designerState.guestCount ? getRecommendedBand(designerState.guestCount) : null;
  const customEvent = recommended ? recommended.band === "CUSTOM_EVENT" : false;

  return {
    valid: missing.length === 0 && !customEvent,
    missing,
    customEvent,
  };
}
