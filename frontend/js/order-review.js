// CakeCraft Studio — Order Review page.
// Reconstructs a designerState-shaped object from the URL (a template id
// plus the four selected option ids) using the existing getDesignerInit
// API call, then reuses the existing Designer utility modules — pricing.js,
// summary.js, validation.js — to render it. No business logic here, no
// pricing/summary/validation rules duplicated.

function getOrderReviewParamsFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return {
    templateId: params.get("id"),
    cakeSizeId: params.get("cakeSize"),
    flavorId: params.get("flavor"),
    fillingId: params.get("filling"),
    frostingId: params.get("frosting"),
  };
}

function findOptionById(items, id) {
  if (!items || !id) return null;
  return items.find((item) => item.id === id) || null;
}

function renderOrderReviewLoading() {
  const nameEl = document.getElementById("reviewTemplateName");
  if (nameEl) nameEl.textContent = "Loading your order...";
}

function renderOrderReviewError() {
  const nameEl = document.getElementById("reviewTemplateName");
  if (nameEl) nameEl.textContent = "Unable to load your order. Please return to the Designer.";
}

// The only function that writes to the Order Review DOM. Everything it
// displays comes from the existing utility modules, not from logic here.
function renderOrderReview(designerState) {
  const summary = buildOrderSummary(designerState);
  const price = calculateCurrentPrice(designerState);
  const servingRange = getServingRange(designerState);
  const validation = validateOrder(designerState);

  const img = document.getElementById("reviewTemplateImage");
  const nameEl = document.getElementById("reviewTemplateName");
  const sizeEl = document.getElementById("reviewCakeSize");
  const flavorEl = document.getElementById("reviewFlavor");
  const fillingEl = document.getElementById("reviewFilling");
  const frostingEl = document.getElementById("reviewFrosting");
  const priceEl = document.getElementById("reviewPrice");
  const servingsEl = document.getElementById("reviewServingRange");
  const continueBtn = document.getElementById("continueToCustomerInfoBtn");

  if (img && designerState.template) {
    img.src = designerState.template.preview_image
      ? `assets/images/${designerState.template.preview_image}`
      : "assets/images/hero-cake.svg";
    img.alt = `${designerState.template.name} cake`;
  }

  if (nameEl) nameEl.textContent = summary.templateName;
  if (sizeEl) sizeEl.textContent = summary.cakeSize;
  if (flavorEl) flavorEl.textContent = summary.flavor;
  if (fillingEl) fillingEl.textContent = summary.filling;
  if (frostingEl) frostingEl.textContent = summary.frosting;
  if (priceEl) priceEl.textContent = `$${price.toFixed(2)}`;
  if (servingsEl) servingsEl.textContent = servingRange;
  if (continueBtn) continueBtn.disabled = !validation.valid;
}

async function loadOrderReview() {
  const { templateId, cakeSizeId, flavorId, fillingId, frostingId } = getOrderReviewParamsFromUrl();

  if (!templateId) {
    renderOrderReviewError();
    return;
  }

  renderOrderReviewLoading();

  try {
    const response = await getDesignerInit(templateId);
    const options = response.options;

    const designerState = {
      template: response.template,
      cakeSize: findOptionById(options.cake_sizes, cakeSizeId),
      flavor: findOptionById(options.flavors, flavorId),
      filling: findOptionById(options.fillings, fillingId),
      frosting: findOptionById(options.frostings, frostingId),
    };

    renderOrderReview(designerState);
  } catch (error) {
    renderOrderReviewError();
  }
}

function initReturnToDesignerButton() {
  const button = document.getElementById("returnToDesignerBtn");
  if (!button) return;
  button.addEventListener("click", () => {
    const { templateId } = getOrderReviewParamsFromUrl();
    window.location.href = `designer.html?id=${encodeURIComponent(templateId)}`;
  });
}

function initContinueToCustomerInfoButton() {
  const button = document.getElementById("continueToCustomerInfoBtn");
  if (!button) return;
  button.addEventListener("click", () => {
    window.location.href = `customer-information.html${window.location.search}`;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  loadOrderReview();
  initReturnToDesignerButton();
  initContinueToCustomerInfoButton();
});
