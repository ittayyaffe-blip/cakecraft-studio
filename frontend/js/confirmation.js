// CakeCraft Studio — Order Confirmation page.
// Displays the order number returned after submission. No fetch calls,
// no business logic — this page only reads its own URL.

function getOrderIdFromUrl() {
  return new URLSearchParams(window.location.search).get("orderId");
}

function renderConfirmation() {
  const orderId = getOrderIdFromUrl();
  const orderIdEl = document.getElementById("confirmationOrderId");
  if (orderIdEl) {
    orderIdEl.textContent = orderId ? `#${orderId}` : "Order number unavailable";
  }
}

document.addEventListener("DOMContentLoaded", renderConfirmation);
