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

function validateOrder(designerState) {
  const missing = REQUIRED_FIELDS.filter((field) => !designerState[field.key]).map(
    (field) => field.label
  );

  return {
    valid: missing.length === 0,
    missing,
  };
}
