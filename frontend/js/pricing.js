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
