// CakeCraft Studio — order summary builder. Pure function only: given a
// designerState, describe the current selections and return a plain object.
// No DOM access, no fetches, no HTML, no pricing. This is the one place
// summary-shaping logic is allowed to live — extend here (decoration,
// inscription, delivery date, etc.), never in the UI code.

const NOT_SELECTED = "Not selected";

function buildOrderSummary(designerState) {
  return {
    templateName: designerState.template ? designerState.template.name : NOT_SELECTED,
    cakeSize: designerState.cakeSize ? designerState.cakeSize.name : NOT_SELECTED,
    flavor: designerState.flavor ? designerState.flavor.name : NOT_SELECTED,
    filling: designerState.filling ? designerState.filling.name : NOT_SELECTED,
    frosting: designerState.frosting ? designerState.frosting.name : NOT_SELECTED,
  };
}
