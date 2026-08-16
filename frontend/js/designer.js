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
  // Servings + Event Pricing: the primary business input -- a plain
  // number, not an option object like the others above, since it has no
  // catalog id of its own.
  guestCount: null,
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
  // Lets Custom Event mode hide/show one specific group (Cake Size) by id
  // -- see refreshValidation()'s cake_sizeOptionGroup lookup below.
  fieldset.id = `${groupName}OptionGroup`;
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
// Custom Event UX fix: 76+ guests have no standard dollar figure at all
// (not $0, not the template base price, not a stale prior standard
// price) -- the standard price/serving-range block is hidden entirely
// and replaced with a fixed "Tailored proposal" note.
function refreshPricing() {
  const standardBlock = document.getElementById("standardPricingBlock");
  const customEventNote = document.getElementById("customEventPricingNote");
  const validation = validateOrder(designerState);

  if (standardBlock) standardBlock.hidden = validation.customEvent;
  if (customEventNote) customEventNote.hidden = !validation.customEvent;
  if (validation.customEvent) return;

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
// Custom Event UX fix: a 76+ guest count is an intentional, permanent
// state for this session, not a customer who forgot to pick a size --
// the standard "Size: ..." panel is replaced with a dedicated Guests/
// Order Type/Pricing panel rather than ever showing "Size: Not selected".
function refreshSummary() {
  const summary = buildOrderSummary(designerState);
  const validation = validateOrder(designerState);

  const standardPanel = document.getElementById("standardSummaryPanel");
  const customEventPanel = document.getElementById("customEventSummaryPanel");
  const guestCountEl = document.getElementById("summaryGuestCount");

  if (standardPanel) standardPanel.hidden = validation.customEvent;
  if (customEventPanel) customEventPanel.hidden = !validation.customEvent;
  if (guestCountEl) guestCountEl.textContent = designerState.guestCount ?? "";
  if (validation.customEvent) return;

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
  const customEventNotice = document.getElementById("customEventNotice");
  const customEventMessageEl = document.getElementById("customEventMessage");
  const cakeSizeGroup = document.getElementById("cake_sizeOptionGroup");

  if (statusEl) {
    statusEl.textContent = validation.customEvent
      ? "✋ Tailored proposal needed"
      : validation.valid
        ? "✅ Ready to order"
        : "❌ Missing";
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

  // Servings + Event Pricing: 76+ guests must never reach normal
  // automated checkout, regardless of how complete every other field is
  // -- the Continue button stays disabled and the tailored-proposal
  // notice replaces it as the only next step.
  if (customEventNotice) customEventNotice.hidden = !validation.customEvent;
  if (customEventMessageEl && validation.customEvent) customEventMessageEl.textContent = CUSTOM_EVENT_MESSAGE;

  // Custom Event UX fix: 76+ guests can't be allowed to select (or leave
  // selected) a standard size at all -- hiding the whole Cake Size group
  // is the smallest clean way to make that impossible, vs. disabling
  // every radio individually. clearSizeSelection() (called from
  // refreshGuestCountRecommendation whenever the band is CUSTOM_EVENT)
  // already guarantees nothing stays checked underneath.
  if (cakeSizeGroup) cakeSizeGroup.hidden = validation.customEvent;

  if (startDesigningBtn) {
    startDesigningBtn.disabled = !validation.valid;
    startDesigningBtn.hidden = validation.customEvent;
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

  // Serving Guide UX fix: guest count is authoritative over manual size
  // clicks too, not just the initial recommendation -- a click that
  // conflicts with (or happens during) a stated guest count is corrected
  // back rather than left to create a mismatched size/guest-count pair.
  // Reuses the same getRecommendedBand/selectSizeRadioByName helpers as
  // refreshGuestCountRecommendation -- no second threshold table.
  if (group.key === "cake_sizes" && designerState.guestCount) {
    const recommended = getRecommendedBand(designerState.guestCount);
    if (recommended && recommended.band === "CUSTOM_EVENT") {
      clearSizeSelection();
      return;
    }
    if (recommended && designerState.cakeSize?.name !== recommended.sizeName) {
      selectSizeRadioByName(recommended.sizeName);
      return;
    }
  }

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

// Servings + Event Pricing: guest count drives size selection, not the
// other way around -- this only ever programmatically checks the
// already-rendered radio matching the recommended band and dispatches a
// real "change" event, reusing handleOptionChange's own existing
// delegation (container.addEventListener("change", ...)) rather than
// duplicating its state-update/refresh logic here. No-ops safely if the
// catalog hasn't finished loading yet or the named size isn't found.
function selectSizeRadioByName(sizeName) {
  if (!designerOptions) return;
  const match = designerOptions.cake_sizes.find((size) => size.name === sizeName);
  const container = document.getElementById("designerOptionsContainer");
  if (!match || !container) return;

  const radio = container.querySelector(`input[name="cake_size"][value="${match.id}"]`);
  if (!radio || radio.checked) return;
  radio.checked = true;
  radio.dispatchEvent(new Event("change", { bubbles: true }));
}

// Serving Guide UX fix: the inverse of selectSizeRadioByName -- unchecks
// whatever cake_size radio is currently checked and clears
// designerState.cakeSize. Programmatic uncheck doesn't fire a "change"
// event on its own, so this refreshes the dependent panels directly
// (mirrors handleOptionChange's own refresh calls) instead of relying on
// delegation.
//
// Custom Event flow repair -- root cause of the "$290 shown for 100
// guests" bug: this used to skip the three refreshes whenever cakeSize
// was ALREADY null (e.g. a customer typing straight into an untouched
// guest-count field), on the assumption there was nothing to update.
// That's no longer true -- refreshPricing/refreshSummary now ALSO have
// to switch into their Custom Event display (hide the standard price/
// summary, show "Tailored proposal") purely because the guest count
// entered Custom Event range, independent of whether a size was ever
// selected. Always refresh; the DOM writes are cheap and idempotent.
function clearSizeSelection() {
  const container = document.getElementById("designerOptionsContainer");
  const checked = container && container.querySelector('input[name="cake_size"]:checked');
  if (checked) checked.checked = false;

  designerState.cakeSize = null;
  refreshPricing();
  refreshSummary();
  refreshValidation();
}

function refreshGuestCountRecommendation() {
  const recommendationEl = document.getElementById("guestCountRecommendation");
  if (!recommendationEl) return;

  const recommended = designerState.guestCount ? getRecommendedBand(designerState.guestCount) : null;

  // 76+: no standard size is ever correct, so any stale selection (e.g.
  // "Small" auto-picked while typing "1" of "100") must be cleared, not
  // just hidden from the recommendation hint.
  if (recommended && recommended.band === "CUSTOM_EVENT") {
    recommendationEl.hidden = true;
    clearSizeSelection();
    return;
  }

  if (!recommended) {
    recommendationEl.hidden = true;
    return;
  }

  recommendationEl.textContent = `Recommended size: ${recommended.sizeName}`;
  recommendationEl.hidden = false;
  selectSizeRadioByName(recommended.sizeName);
}

function initGuestCountField() {
  const input = document.getElementById("guestCount");
  if (!input) return;
  input.addEventListener("input", () => {
    const value = parseInt(input.value, 10);
    designerState.guestCount = Number.isInteger(value) && value > 0 ? value : null;
    refreshGuestCountRecommendation();
    refreshValidation();
  });
}

function initStartDesigningButton() {
  const button = document.getElementById("startDesigningBtn");
  if (!button) return;
  button.addEventListener("click", () => {
    // The button is disabled by refreshValidation() until designerState is
    // complete (which now also requires a standard, non-custom-event
    // guestCount), so every property read here is guaranteed to be
    // populated. guestCount rides along in the URL the exact same way
    // every other selection already does -- order-review.html forwards
    // its own full query string on to customer-information.html
    // unchanged, so no other page needs to know this field exists.
    const params = new URLSearchParams({
      id: designerState.template.id,
      cakeSize: designerState.cakeSize.id,
      flavor: designerState.flavor.id,
      filling: designerState.filling.id,
      frosting: designerState.frosting.id,
      guestCount: designerState.guestCount,
    });
    window.location.href = `order-review.html?${params.toString()}`;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  loadDesigner();
  initDesignerStateTracking();
  initStartDesigningButton();
  initGuestCountField();
});
