// CakeCraft Studio — Cake Designer foundation page.
// Reads the template id from the URL, calls the API, and renders template details.
// No fetch calls here (getDesignerInit lives in api.js). No editing, no AI, yet.

// Populated by loadDesigner() on page load; rendered into option groups
// below, and read by future milestones (pricing, etc.).
let designerOptions = null;

// Maps each designerOptions key to its fieldset legend, radio group name,
// and the designerState property it controls.
const OPTION_GROUPS = [
  { key: "cake_sizes", legend: "Cake Size", name: "cake_size", stateKey: "cakeSize" },
  { key: "flavors", legend: "Flavor", name: "flavor", stateKey: "flavor" },
  { key: "fillings", legend: "Filling", name: "filling", stateKey: "filling" },
  { key: "frostings", legend: "Frosting", name: "frosting", stateKey: "frosting" },
];

// The user's current cake configuration. Selections are stored as the full
// option object (not just the id) so later milestones (pricing, summary, etc.)
// can read names/prices straight off of it.
const designerState = {
  template: null,
  cakeSize: null,
  flavor: null,
  filling: null,
  frosting: null,
};

function getTemplateIdFromUrl() {
  return new URLSearchParams(window.location.search).get("id");
}

// The loading state (a shimmering skeleton over the image card and title,
// details panel hidden) is the default markup in designer.html, so there's
// never a flash of a generic placeholder photo or bare "Loading..." text
// before this even runs — this just re-asserts it defensively.
function renderTemplateLoading() {
  const imageCard = document.getElementById("templateImageCard");
  const nameEl = document.getElementById("templateName");
  const detailsEl = document.getElementById("designerDetails");

  if (imageCard) imageCard.classList.add("is-loading");
  if (nameEl) {
    nameEl.classList.add("is-loading");
    nameEl.textContent = "Loading cake template…";
  }
  if (detailsEl) detailsEl.classList.add("is-hidden");
}

function renderTemplateError() {
  const imageCard = document.getElementById("templateImageCard");
  const nameEl = document.getElementById("templateName");
  const detailsEl = document.getElementById("designerDetails");

  // Both loading-skeleton classes have to come off here too, not just on
  // success — the skeleton's CSS renders #templateName's text transparent,
  // so leaving .is-loading on would silently hide this very error message.
  if (imageCard) imageCard.classList.remove("is-loading");
  if (nameEl) {
    nameEl.classList.remove("is-loading");
    nameEl.textContent = "Unable to load this cake template. Please try again later.";
  }
  if (detailsEl) detailsEl.classList.add("is-hidden");
}

function renderTemplateDetail(template) {
  const imageCard = document.getElementById("templateImageCard");
  const img = document.getElementById("templateImage");
  const nameEl = document.getElementById("templateName");
  const collectionEl = document.getElementById("templateCollection");
  const styleEl = document.getElementById("templateStyle");
  const priceEl = document.getElementById("templateBasePrice");
  const detailsEl = document.getElementById("designerDetails");

  if (img) {
    img.src = template.preview_image
      ? `assets/images/${template.preview_image}`
      : "assets/images/hero-cake.svg";
    img.alt = `${template.name} cake template`;
  }
  if (imageCard) imageCard.classList.remove("is-loading");
  if (nameEl) {
    nameEl.classList.remove("is-loading");
    nameEl.textContent = template.name;
  }
  if (collectionEl) collectionEl.textContent = template.category;
  if (styleEl) styleEl.textContent = template.style;
  if (priceEl) priceEl.textContent = `$${template.base_price.toFixed(2)}`;
  if (detailsEl) detailsEl.classList.remove("is-hidden");
}

function createOptionGroup(legendText, groupName, items) {
  const fieldset = document.createElement("fieldset");
  fieldset.className = "option-group";
  // <legend> can never be repositioned via CSS (browsers anchor it to the
  // fieldset border regardless of margin), so the heading is a styled div
  // instead. aria-label on the fieldset preserves the accessible group name
  // that <legend> would otherwise have provided.
  fieldset.setAttribute("aria-label", legendText);

  const legend = document.createElement("div");
  legend.className = "option-group__heading";
  legend.textContent = legendText;
  fieldset.appendChild(legend);

  items.forEach((item) => {
    const label = document.createElement("label");

    const input = document.createElement("input");
    input.type = "radio";
    input.name = groupName;
    input.value = item.id;

    label.append(input, ` ${item.name}`);
    fieldset.appendChild(label);
  });

  return fieldset;
}

function renderDesignerOptions(options) {
  const container = document.getElementById("designerOptionsContainer");
  if (!container) return;

  container.innerHTML = "";
  OPTION_GROUPS.forEach((group) => {
    container.appendChild(createOptionGroup(group.legend, group.name, options[group.key]));
  });
}

// Reads designerState through pricing.js (the only place pricing math is
// allowed to happen) and writes the result into the DOM. No calculation here.
function refreshPricing() {
  const priceEl = document.getElementById("currentPrice");
  const servingsEl = document.getElementById("servingRange");

  const price = calculateCurrentPrice(designerState);
  const servingRange = getServingRange(designerState);

  if (priceEl) priceEl.textContent = `$${price.toFixed(2)}`;
  if (servingsEl) servingsEl.textContent = servingRange;
}

// Reads designerState through summary.js (the only place summary-shaping
// logic is allowed to happen) and writes the result into the DOM. This is
// the only function that updates the Order Summary section.
function refreshSummary() {
  const summary = buildOrderSummary(designerState);

  const nameEl = document.getElementById("summaryTemplateName");
  const sizeEl = document.getElementById("summaryCakeSize");
  const flavorEl = document.getElementById("summaryFlavor");
  const fillingEl = document.getElementById("summaryFilling");
  const frostingEl = document.getElementById("summaryFrosting");

  if (nameEl) nameEl.textContent = summary.templateName;
  if (sizeEl) sizeEl.textContent = summary.cakeSize;
  if (flavorEl) flavorEl.textContent = summary.flavor;
  if (fillingEl) fillingEl.textContent = summary.filling;
  if (frostingEl) frostingEl.textContent = summary.frosting;
}

// Reads designerState through validation.js (the only place validation
// rules are allowed to live) and writes the result into the DOM. This is
// the only function that updates the Order Status section or the
// Start Designing button's disabled state.
function refreshValidation() {
  const validation = validateOrder(designerState);

  const statusEl = document.getElementById("validationStatus");
  const missingListEl = document.getElementById("validationMissingList");
  const startDesigningBtn = document.getElementById("startDesigningBtn");

  if (statusEl) {
    statusEl.textContent = validation.valid ? "✅ Ready to order" : "❌ Missing";
  }

  if (missingListEl) {
    missingListEl.innerHTML = "";
    validation.missing.forEach((label) => {
      const item = document.createElement("li");
      item.className = "section-subtitle";
      item.textContent = label;
      missingListEl.appendChild(item);
    });
  }

  if (startDesigningBtn) {
    startDesigningBtn.disabled = !validation.valid;
  }
}

async function loadDesigner() {
  const id = getTemplateIdFromUrl();
  if (!id) {
    renderTemplateError();
    return;
  }

  renderTemplateLoading();

  try {
    const response = await getDesignerInit(id);
    designerOptions = response.options;
    designerState.template = response.template;
    renderTemplateDetail(response.template);
    renderDesignerOptions(designerOptions);
    refreshPricing();
    refreshSummary();
    refreshValidation();
  } catch (error) {
    renderTemplateError();
  }
}

// One reusable handler for every option group, via event delegation on the
// shared container — a change anywhere inside it bubbles up here once,
// regardless of how many radios exist.
function handleOptionChange(event) {
  const input = event.target;
  if (!(input instanceof HTMLInputElement) || input.type !== "radio") return;

  const group = OPTION_GROUPS.find((g) => g.name === input.name);
  if (!group || !designerOptions) return;

  designerState[group.stateKey] = designerOptions[group.key].find(
    (item) => item.id === input.value
  );

  refreshPricing();
  refreshSummary();
  refreshValidation();
  console.log(designerState);
}

function initDesignerStateTracking() {
  const container = document.getElementById("designerOptionsContainer");
  if (!container) return;
  container.addEventListener("change", handleOptionChange);
}

function initStartDesigningButton() {
  const button = document.getElementById("startDesigningBtn");
  if (!button) return;
  button.addEventListener("click", () => {
    // The button is disabled by refreshValidation() until designerState is
    // complete, so every property read here is guaranteed to be populated.
    const params = new URLSearchParams({
      id: designerState.template.id,
      cakeSize: designerState.cakeSize.id,
      flavor: designerState.flavor.id,
      filling: designerState.filling.id,
      frosting: designerState.frosting.id,
    });
    window.location.href = `order-review.html?${params.toString()}`;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  loadDesigner();
  initDesignerStateTracking();
  initStartDesigningButton();
});
