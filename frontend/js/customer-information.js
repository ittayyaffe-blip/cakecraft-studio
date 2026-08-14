// CakeCraft Studio — Customer Information page.
// Collects the customer's contact details before order submission.
// All validation logic lives here — the HTML only declares the rules
// (required, type="email") natively; this file reads the native result.
// No pricing/summary/order-validation logic from the Designer flow is
// touched or duplicated — this page only validates its own form and
// forwards the order (createOrder lives in api.js).

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
});
