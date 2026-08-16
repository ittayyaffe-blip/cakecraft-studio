// CakeCraft Studio — Order Review page.
// Reconstructs a designerState-shaped object from the URL (a template id
// plus the four selected option ids) using the existing getDesignerInit
// API call, then reuses the existing Designer utility modules — pricing.js,
// summary.js, validation.js — to render it. No business logic here, no
// pricing/summary/validation rules duplicated.

function getOrderReviewParamsFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const guestCountRaw = parseInt(params.get("guestCount"), 10);
  return {
    templateId: params.get("id"),
    cakeSizeId: params.get("cakeSize"),
    flavorId: params.get("flavor"),
    fillingId: params.get("filling"),
    frostingId: params.get("frosting"),
    guestCount: Number.isInteger(guestCountRaw) && guestCountRaw > 0 ? guestCountRaw : null,
  };
}

function findOptionById(items, id) {
  if (!items || !id) return null;
  return items.find((item) => item.id === id) || null;
}

// Route/state guard: guest count is authoritative here too, exactly like
// the Designer's own handleOptionChange and the backend's create_order().
// The URL's own cakeSize param is never trusted directly whenever a guest
// count is present -- this is what makes a stale/manually-edited cakeSize
// query param (or a Back/Forward navigation to an old URL) impossible to
// present as a valid order: the size shown always matches the guest count,
// never whatever the URL happened to say. Returns null for CUSTOM_EVENT
// (76+) since no standard size is ever correct there.
function findSizeForGuestCount(cakeSizes, guestCount) {
  const recommended = getRecommendedBand(guestCount);
  if (!recommended || !recommended.sizeName) return null;
  return cakeSizes.find((size) => size.name === recommended.sizeName) || null;
}

function renderOrderReviewLoading() {
  const nameEl = document.getElementById("reviewTemplateName");
  if (nameEl) nameEl.textContent = "Loading your order...";
}

function renderOrderReviewError() {
  const nameEl = document.getElementById("reviewTemplateName");
  if (nameEl) nameEl.textContent = "Unable to load your order. Please return to the Designer.";

  const imageWrapEl = document.getElementById("reviewImageWrap");
  if (imageWrapEl) imageWrapEl.classList.add("is-hidden");

  const detailsEl = document.getElementById("reviewDetails");
  if (detailsEl) detailsEl.classList.add("is-hidden");

  const continueBtn = document.getElementById("continueToCustomerInfoBtn");
  if (continueBtn) continueBtn.classList.add("is-hidden");
}

// The only function that writes to the Order Review DOM. Everything it
// displays comes from the existing utility modules, not from logic here.
// Route/state guard: a Custom Event guest count (76+, or however it got
// into designerState.guestCount -- stale URL, Back/Forward, a manually
// edited query param) never renders a standard size/price as if it were
// a valid order. It gets the exact same Custom Event treatment the
// Designer already gives it.
function renderOrderReview(designerState) {
  const summary = buildOrderSummary(designerState);
  const price = calculateCurrentPrice(designerState);
  const servingRange = getServingRange(designerState);
  const validation = validateOrder(designerState);

  const img = document.getElementById("reviewTemplateImage");
  const nameEl = document.getElementById("reviewTemplateName");
  const guestCountEl = document.getElementById("reviewGuestCount");
  const sizeEl = document.getElementById("reviewCakeSize");
  const flavorEl = document.getElementById("reviewFlavor");
  const fillingEl = document.getElementById("reviewFilling");
  const frostingEl = document.getElementById("reviewFrosting");
  const priceEl = document.getElementById("reviewPrice");
  const servingsEl = document.getElementById("reviewServingRange");
  const continueBtn = document.getElementById("continueToCustomerInfoBtn");
  const standardDetailsEl = document.getElementById("reviewStandardDetails");
  const customEventNotice = document.getElementById("customEventNotice");
  const customEventMessageEl = document.getElementById("customEventMessage");

  if (img && designerState.template) {
    img.src = designerState.template.preview_image
      ? `assets/images/${designerState.template.preview_image}`
      : "assets/images/hero-cake.svg";
    img.alt = `${designerState.template.name} cake`;
  }

  if (nameEl) nameEl.textContent = summary.templateName;
  if (guestCountEl) guestCountEl.textContent = designerState.guestCount ?? "Not provided";

  if (standardDetailsEl) standardDetailsEl.hidden = validation.customEvent;
  if (customEventNotice) customEventNotice.hidden = !validation.customEvent;
  if (customEventMessageEl && validation.customEvent) customEventMessageEl.textContent = CUSTOM_EVENT_MESSAGE;

  if (continueBtn) {
    continueBtn.disabled = !validation.valid;
    continueBtn.hidden = validation.customEvent;
  }

  if (validation.customEvent) return;

  if (sizeEl) sizeEl.textContent = summary.cakeSize;
  if (flavorEl) flavorEl.textContent = summary.flavor;
  if (fillingEl) fillingEl.textContent = summary.filling;
  if (frostingEl) frostingEl.textContent = summary.frosting;
  if (priceEl) priceEl.textContent = `$${price.toFixed(2)}`;
  if (servingsEl) servingsEl.textContent = servingRange;
}

async function loadOrderReview() {
  const { templateId, cakeSizeId, flavorId, fillingId, frostingId, guestCount } = getOrderReviewParamsFromUrl();

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
      // Guest count present -> it alone decides the size (see
      // findSizeForGuestCount's own note); no guest count at all is a
      // defensive fallback for a URL that somehow predates this field.
      cakeSize: guestCount
        ? findSizeForGuestCount(options.cake_sizes, guestCount)
        : findOptionById(options.cake_sizes, cakeSizeId),
      flavor: findOptionById(options.flavors, flavorId),
      filling: findOptionById(options.fillings, fillingId),
      frosting: findOptionById(options.frostings, frostingId),
      guestCount,
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
