// CakeCraft Studio — Payment page (payment.html).
// Simulated/demo payment only: no card fields exist anywhere on this page
// on purpose (see payment_service.py's own docstring) -- a polished
// summary card with one explicit "Pay Now" button is the entire flow.
// All rendering here builds DOM nodes via createElement/textContent for
// any value that could contain customer/order data, same convention as
// every other customer-facing page (see admin-orders.js's own note).

function getOrderIdFromUrl() {
  return new URLSearchParams(window.location.search).get("order");
}

function formatCurrency(amount) {
  return `$${Number(amount).toFixed(2)}`;
}

function appendConfigRow(container, label, value) {
  const row = document.createElement("p");
  row.className = "section-subtitle";
  row.textContent = `${label}: ${value}`;
  container.appendChild(row);
}

function renderOrderSummary(order) {
  document.getElementById("paymentOrderId").textContent = `#${order.orderId}`;
  document.getElementById("paymentTotal").textContent = `Total: ${formatCurrency(order.totalPrice)}`;

  const configList = document.getElementById("paymentConfigList");
  configList.innerHTML = "";
  if (order.templateName) {
    appendConfigRow(configList, "Design", order.templateName);
  }
  Object.entries(order.configuration || {}).forEach(([key, option]) => {
    if (option && option.name) appendConfigRow(configList, key, option.name);
  });
}

function showPaymentSuccess(orderId, referenceText) {
  document.getElementById("paymentSummary").classList.add("is-hidden");
  document.getElementById("paymentReference").textContent = referenceText;
  document.getElementById("paymentContinueBtn").href = `confirmation.html?orderId=${encodeURIComponent(orderId)}`;
  document.getElementById("paymentSuccess").classList.remove("is-hidden");
}

async function handlePayNow(orderId) {
  const btn = document.getElementById("payNowBtn");
  const errorEl = document.getElementById("paymentError");
  btn.disabled = true;
  errorEl.classList.add("is-hidden");

  try {
    const result = await payOrder(orderId);
    showPaymentSuccess(
      orderId,
      `Demo transaction reference: ${result.simulatedReference} — Total paid: ${formatCurrency(result.amount)}`
    );
  } catch (error) {
    errorEl.textContent = "Payment could not be processed. Please try again.";
    errorEl.classList.remove("is-hidden");
    btn.disabled = false;
  }
}

async function loadOrder() {
  const orderId = getOrderIdFromUrl();
  const loading = document.getElementById("paymentLoading");
  const errorEl = document.getElementById("paymentError");

  if (!orderId) {
    loading.classList.add("is-hidden");
    errorEl.textContent = "No order reference was provided.";
    errorEl.classList.remove("is-hidden");
    return;
  }

  try {
    const order = await getOrder(orderId);
    loading.classList.add("is-hidden");
    renderOrderSummary(order);

    if (order.paymentStatus === "paid") {
      showPaymentSuccess(orderId, "This order has already been paid (simulated).");
      return;
    }

    document.getElementById("paymentStatusLine").textContent = "Payment status: Pending";
    document.getElementById("paymentSummary").classList.remove("is-hidden");
    document.getElementById("payNowBtn").addEventListener("click", () => handlePayNow(orderId));
  } catch (error) {
    loading.classList.add("is-hidden");
    errorEl.textContent = "Unable to load this order. Please check your link, or contact us directly.";
    errorEl.classList.remove("is-hidden");
  }
}

document.addEventListener("DOMContentLoaded", loadOrder);
