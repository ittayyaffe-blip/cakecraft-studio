// CakeCraft Studio — Customer Information page.
// Collects the customer's contact details before order submission.
// All validation logic lives here — the HTML only declares the rules
// (required, type="email") natively; this file reads the native result.
// No pricing/summary/order-validation logic from the Designer flow is
// touched or duplicated — this page only validates its own form and
// forwards the order (createOrder lives in api.js).
//
// Pickup scheduling (Pickup Date + Order Priority, Phase 2): the backend
// is authoritative for every hard rule (past date, Monday, business
// hours — see order_service.validate_pickup_datetime). Everything here
// is UX convenience only: native min/max attributes, a Monday check via
// setCustomValidity (so it plugs into the exact same form.checkValidity()
// gate every other field already uses, no parallel validation system),
// and an informational (never blocking) rush-order warning.

// Mirrors backend/app/services/order_service.py's _CATEGORY_MIN_LEAD_DAYS
// exactly — duplicated here deliberately, same convention ui-helpers.js's
// own NOTIFICATION_EVENT_LABELS already uses for presentation-only static
// data with no reason to round-trip the network for. This copy is never
// authoritative: the real accept/reject decision is always the backend's
// (see validate_pickup_datetime), this only drives an optional heads-up.
const CATEGORY_MIN_LEAD_DAYS = {
  Birthday: 2,
  "Baby Shower": 2,
  Graduation: 2,
  Corporate: 3,
  Wedding: 14,
};

function getOrderContextFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return {
    templateId: params.get("id"),
    cakeSizeId: params.get("cakeSize"),
    flavorId: params.get("flavor"),
    fillingId: params.get("filling"),
    frostingId: params.get("frosting"),
  };
}

function todayLocalIsoDate() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

// Date-only ISO strings ("YYYY-MM-DD") are timezone-ambiguous if handed
// straight to `new Date(...)` — parsed manually against UTC here so the
// weekday check never shifts by a day depending on the browser's own
// timezone offset.
function isMondayIsoDate(isoDate) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).getUTCDay() === 1;
}

function daysUntil(isoDate) {
  const [year, month, day] = isoDate.split("-").map(Number);
  const target = Date.UTC(year, month - 1, day);
  const [ty, tm, td] = todayLocalIsoDate().split("-").map(Number);
  const today = Date.UTC(ty, tm - 1, td);
  return Math.round((target - today) / (24 * 60 * 60 * 1000));
}

let _templateCategory = null;

function initPickupFields() {
  const dateInput = document.getElementById("pickupDate");
  const warningEl = document.getElementById("pickupRushWarning");
  if (!dateInput) return;

  dateInput.min = todayLocalIsoDate();

  function refreshPickupValidity() {
    if (dateInput.value && isMondayIsoDate(dateInput.value)) {
      dateInput.setCustomValidity("We're closed Mondays — please choose Tuesday through Sunday.");
    } else {
      dateInput.setCustomValidity("");
    }
    refreshRushWarning();
  }

  function refreshRushWarning() {
    if (!warningEl) return;
    const minDays = _templateCategory ? CATEGORY_MIN_LEAD_DAYS[_templateCategory] : null;
    if (!dateInput.value || !dateInput.checkValidity() || minDays == null) {
      warningEl.hidden = true;
      return;
    }
    const days = daysUntil(dateInput.value);
    if (days >= 0 && days < minDays) {
      warningEl.textContent =
        "This pickup date is inside our usual preparation window. We'll treat it as a rush request and " +
        "availability may require bakery attention.";
      warningEl.hidden = false;
    } else {
      warningEl.hidden = true;
    }
  }

  dateInput.addEventListener("input", refreshPickupValidity);
  dateInput.addEventListener("change", refreshPickupValidity);
}

async function loadTemplateCategoryForRushWarning(templateId) {
  if (!templateId) return;
  try {
    const { template } = await getDesignerInit(templateId);
    _templateCategory = template ? template.category : null;
  } catch (error) {
    // Non-critical: the rush warning is informational only. The backend
    // still enforces everything that actually matters.
    _templateCategory = null;
  }
}

function renderSubmitError(message) {
  const errorEl = document.getElementById("customerInfoError");
  if (errorEl) errorEl.textContent = message;
}

function isFormValid() {
  const form = document.getElementById("customerInfoForm");
  return form ? form.checkValidity() : false;
}

// The only function that updates the Submit button's disabled state.
function refreshSubmitButtonState() {
  const submitBtn = document.getElementById("submitOrderBtn");
  if (submitBtn) submitBtn.disabled = !isFormValid();
}

function initFormValidation() {
  const form = document.getElementById("customerInfoForm");
  if (!form) return;

  form.addEventListener("input", refreshSubmitButtonState);
  form.addEventListener("submit", (event) => event.preventDefault());
  refreshSubmitButtonState();
}

function initBackButton() {
  const button = document.getElementById("backToOrderReviewBtn");
  if (!button) return;
  button.addEventListener("click", () => {
    window.location.href = `order-review.html${window.location.search}`;
  });
}

function initSubmitButton() {
  const button = document.getElementById("submitOrderBtn");
  if (!button) return;

  button.addEventListener("click", async () => {
    const context = getOrderContextFromUrl();
    if (
      !context.templateId ||
      !context.cakeSizeId ||
      !context.flavorId ||
      !context.fillingId ||
      !context.frostingId
    ) {
      renderSubmitError("Your order details are missing. Please start again from the Designer.");
      return;
    }

    const order = {
      template_id: context.templateId,
      cake_size_id: context.cakeSizeId,
      flavor_id: context.flavorId,
      filling_id: context.fillingId,
      frosting_id: context.frostingId,
      customer_name: document.getElementById("customerName").value,
      customer_phone: document.getElementById("customerPhone").value,
      customer_email: document.getElementById("customerEmail").value,
      notes: document.getElementById("customerNotes").value || null,
      pickup_date: document.getElementById("pickupDate").value,
      pickup_time: document.getElementById("pickupTime").value,
    };

    renderSubmitError("");
    button.disabled = true;

    try {
      const response = await createOrder(order);
      // Order is created as `pending`; payment is a separate, explicit
      // step the customer takes on the payment page next -- see
      // payment_service.py's own note on why this never happens
      // automatically right after order creation.
      window.location.href = `payment.html?order=${encodeURIComponent(response.orderId)}`;
    } catch (error) {
      renderSubmitError("Unable to submit your order. Please try again.");
      button.disabled = false;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initFormValidation();
  initBackButton();
  initSubmitButton();
  initPickupFields();
  loadTemplateCategoryForRushWarning(getOrderContextFromUrl().templateId);
});
