// CakeCraft Studio Backoffice — Orders page: search, filter, paginate,
// view details in a slide-in drawer, and update status. Search/status/page
// state lives in the URL query string — same convention the customer-facing
// pages already use (designer.html?id=, templates.html?collection=, etc.).
//
// Every render function builds DOM nodes via createElement + textContent
// rather than innerHTML + interpolation for any value that could contain
// customer-submitted text (name, email, phone, notes come from the public,
// unauthenticated order form) — see admin-dashboard.js for the same rule.

const ORDERS_PAGE_SIZE = 20;
const ALL_STATUSES = ["pending", "confirmed", "in_progress", "ready", "completed", "cancelled"];

function getOrdersStateFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return {
    search: params.get("search") || "",
    status: params.get("status") || "",
    page: Number(params.get("page")) || 1,
    id: params.get("id") || null,
  };
}

function setOrdersStateInUrl(state, { replace = false } = {}) {
  const params = new URLSearchParams();
  if (state.search) params.set("search", state.search);
  if (state.status) params.set("status", state.status);
  if (state.page && state.page !== 1) params.set("page", String(state.page));
  if (state.id) params.set("id", state.id);

  const query = params.toString();
  const url = `${window.location.pathname}${query ? `?${query}` : ""}`;
  if (replace) {
    window.history.replaceState({}, "", url);
  } else {
    window.history.pushState({}, "", url);
  }
}

// --- Orders table ----------------------------------------------------------

function renderOrdersTable(orders) {
  const container = document.getElementById("ordersTableContainer");
  container.innerHTML = "";

  if (orders.length === 0) {
    renderEmptyState(container, "No orders match your search.");
    return;
  }

  const table = document.createElement("table");
  table.className = "admin-table";

  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>Customer</th><th>Cake</th><th>Status</th><th>Total</th><th>Placed</th></tr>";
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  orders.forEach((order) => {
    const tr = document.createElement("tr");
    tr.className = "admin-table__row--clickable";
    tr.tabIndex = 0;

    const customerCell = document.createElement("td");
    customerCell.textContent = order.customers ? order.customers.name : "—";

    const cakeCell = document.createElement("td");
    cakeCell.textContent = order.cake_templates ? order.cake_templates.name : "—";

    const statusCell = document.createElement("td");
    statusCell.appendChild(renderStatusBadge(order.status));

    const totalCell = document.createElement("td");
    totalCell.textContent = formatCurrency(order.total_price);

    const placedCell = document.createElement("td");
    placedCell.textContent = formatDateTime(order.created_at);

    tr.append(customerCell, cakeCell, statusCell, totalCell, placedCell);

    const open = () => openOrderDrawer(order.id);
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        open();
      }
    });

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  container.appendChild(table);
}

function renderPagination(total, page, pageSize) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  document.getElementById("ordersPageInfo").textContent =
    `Page ${page} of ${totalPages} (${total} order${total === 1 ? "" : "s"})`;

  document.getElementById("ordersPrevPage").disabled = page <= 1;
  document.getElementById("ordersNextPage").disabled = page >= totalPages;
}

async function loadOrders() {
  const state = getOrdersStateFromUrl();
  const container = document.getElementById("ordersTableContainer");
  renderLoadingState(container, "Loading orders…");

  document.getElementById("ordersSearchInput").value = state.search;
  document.getElementById("ordersStatusFilter").value = state.status;

  try {
    const result = await getAdminOrders({
      search: state.search || undefined,
      status: state.status || undefined,
      page: state.page,
      pageSize: ORDERS_PAGE_SIZE,
    });
    renderOrdersTable(result.items);
    renderPagination(result.total, result.page, result.pageSize);
  } catch (error) {
    renderErrorState(container, "Unable to load orders. Please try again.");
  }
}

function initFilterForm() {
  const form = document.getElementById("ordersFilterForm");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const search = document.getElementById("ordersSearchInput").value.trim();
    const status = document.getElementById("ordersStatusFilter").value;
    setOrdersStateInUrl({ search, status, page: 1 });
    loadOrders();
  });
}

function initPaginationButtons() {
  document.getElementById("ordersPrevPage").addEventListener("click", () => {
    const state = getOrdersStateFromUrl();
    if (state.page > 1) {
      setOrdersStateInUrl({ ...state, page: state.page - 1 });
      loadOrders();
    }
  });

  document.getElementById("ordersNextPage").addEventListener("click", () => {
    const state = getOrdersStateFromUrl();
    setOrdersStateInUrl({ ...state, page: state.page + 1 });
    loadOrders();
  });
}

// --- Order detail drawer ----------------------------------------------------

// Simulated/demo payment status label -- see app/services/payment_service.py's
// own docstring on why this is a demo-only system (no real card data, no real
// provider, anywhere in this project). `order.payment` is null until the
// customer's first Pay Now attempt (see payment_service.get_or_create_payment).
const PAYMENT_STATUS_LABELS = {
  pending: "Pending",
  paid: "Paid (SIMULATED / DEMO)",
  failed: "Failed",
};

function formatPaymentStatus(payment) {
  if (!payment) return "Not yet initiated";
  return PAYMENT_STATUS_LABELS[payment.status] || payment.status;
}

function appendDetailRow(container, label, value) {
  const row = document.createElement("div");
  row.className = "admin-detail-row";

  const labelEl = document.createElement("span");
  labelEl.className = "admin-detail-row__label";
  labelEl.textContent = label;

  const valueEl = document.createElement("span");
  valueEl.className = "admin-detail-row__value";
  valueEl.textContent = value;

  row.append(labelEl, valueEl);
  container.appendChild(row);
}

function renderOrderDetail(order, { justUpdatedNotificationId = null } = {}) {
  const body = document.getElementById("orderDrawerBody");
  body.innerHTML = "";

  appendDetailRow(body, "Order ID", order.id);
  appendDetailRow(body, "Customer", order.customers ? order.customers.name : "—");
  appendDetailRow(body, "Email", order.customers ? order.customers.email : "—");
  appendDetailRow(body, "Phone", order.customers ? order.customers.phone : "—");
  appendDetailRow(body, "Cake", order.cake_templates ? order.cake_templates.name : "—");
  appendDetailRow(body, "Total", formatCurrency(order.total_price));
  appendDetailRow(body, "Payment", formatPaymentStatus(order.payment));
  if (order.payment && order.payment.status === "paid") {
    appendDetailRow(body, "Paid At", formatDateTime(order.payment.paid_at));
    appendDetailRow(body, "Simulated Reference", order.payment.simulated_reference || "—");
  }
  appendDetailRow(body, "Placed", formatDateTime(order.created_at));
  appendDetailRow(body, "Pickup Date", order.pickup_date || "Not scheduled yet");
  appendDetailRow(body, "Pickup Time", order.pickup_time || "Not scheduled yet");
  appendDetailRow(body, "Notes", order.notes || "—");

  if (order.configuration && Object.keys(order.configuration).length > 0) {
    const heading = document.createElement("h3");
    heading.className = "admin-drawer__section-heading";
    heading.textContent = "Configuration";
    body.appendChild(heading);

    Object.entries(order.configuration).forEach(([key, option]) => {
      appendDetailRow(body, key, option && option.name ? option.name : "—");
    });
  }

  body.appendChild(buildStatusUpdateSection(order));
  body.appendChild(buildCustomerUpdateSection(order, justUpdatedNotificationId));
  body.appendChild(buildAgentDraftSection(order));
}

// Customer Update (drawer section E) -- the status-change-triggered draft
// from the Event-Driven Customer Communication Platform (already created
// server-side, in the same PATCH .../status call as buildStatusUpdateSection's
// button below -- see admin/orders.py's update_order_status route). This
// section never drafts or sends anything itself; it only surfaces what the
// backend just did, with a direct link into the existing Communications
// Workspace so staff never has to go hunt for the right notification in
// the list themselves (Section 7's explicit requirement).
function buildCustomerUpdateSection(order, justUpdatedNotificationId) {
  const section = document.createElement("div");
  section.className = "admin-status-update";

  const heading = document.createElement("h3");
  heading.className = "admin-drawer__section-heading";
  heading.textContent = "Customer Update";
  section.appendChild(heading);

  const message = document.createElement("p");
  message.className = "admin-state";
  message.setAttribute("role", "status");

  if (justUpdatedNotificationId) {
    message.textContent = "Customer update draft created.";
    section.appendChild(message);

    const reviewLink = document.createElement("a");
    reviewLink.className = "btn btn-small";
    reviewLink.href = `admin-notifications.html?id=${encodeURIComponent(justUpdatedNotificationId)}`;
    reviewLink.textContent = "Review in Communications";
    section.appendChild(reviewLink);
  } else {
    message.textContent =
      "Updating the status above creates (or reuses) a customer update draft here — review and send it from Communications.";
    section.appendChild(message);
  }

  return section;
}

// Business Intelligence Layer — lets staff request an AI-drafted
// customer message for this specific order. Always lands as a `draft`
// notification in the existing Notification Queue (see
// agent_service.draft_customer_communication) — this button never sends
// anything itself, it only requests a draft for a human to review.
function buildAgentDraftSection(order) {
  const section = document.createElement("div");
  section.className = "admin-status-update";

  const heading = document.createElement("h3");
  heading.className = "admin-drawer__section-heading";
  heading.textContent = "AI Agent";
  section.appendChild(heading);

  const hint = document.createElement("p");
  hint.className = "admin-briefing__generated";
  hint.textContent = "Draft a customer message for this order — it's added to the Notification Queue for your review, never sent automatically.";
  section.appendChild(hint);

  const channelSelect = document.createElement("select");
  channelSelect.setAttribute("aria-label", "Communication channel");
  channelSelect.className = "admin-agent-draft__channel";
  [
    { value: "email", label: "Email" },
    { value: "whatsapp", label: "WhatsApp" },
  ].forEach(({ value, label }) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    channelSelect.appendChild(option);
  });
  channelSelect.value = "email"; // default channel — staff can change it before drafting

  const instructionInput = document.createElement("input");
  instructionInput.type = "text";
  instructionInput.placeholder = "Optional: what should the message say? (e.g. delay by a day)";
  instructionInput.setAttribute("aria-label", "What should the message say?");
  instructionInput.className = "admin-agent-draft__instruction";

  const draftBtn = document.createElement("button");
  draftBtn.type = "button";
  draftBtn.className = "btn btn-small";
  draftBtn.textContent = "Draft AI Message";

  const resultMsg = document.createElement("p");
  resultMsg.className = "admin-state is-hidden";

  draftBtn.addEventListener("click", async () => {
    draftBtn.disabled = true;
    resultMsg.className = "admin-state";
    resultMsg.setAttribute("role", "status"); // loading
    resultMsg.textContent = "Drafting…";

    try {
      await draftAgentCommunication(order.id, instructionInput.value.trim(), channelSelect.value);
      resultMsg.setAttribute("role", "status"); // success — still informational, not an error
      resultMsg.textContent = "Draft created — review it in the Notification Queue.";
    } catch (error) {
      resultMsg.className = "admin-state admin-state--error";
      resultMsg.setAttribute("role", "alert");
      resultMsg.textContent = error.message || "Unable to draft a message.";
    } finally {
      draftBtn.disabled = false;
    }
  });

  const controls = document.createElement("div");
  controls.className = "admin-status-update__controls";
  controls.append(channelSelect, instructionInput, draftBtn);

  section.append(controls, resultMsg);
  return section;
}

function buildStatusUpdateSection(order) {
  const section = document.createElement("div");
  section.className = "admin-status-update";

  const heading = document.createElement("h3");
  heading.className = "admin-drawer__section-heading";
  heading.textContent = "Update Status";
  section.appendChild(heading);

  const controls = document.createElement("div");
  controls.className = "admin-status-update__controls";

  const select = document.createElement("select");
  select.id = "orderStatusSelect";
  select.setAttribute("aria-label", "Order status");
  ALL_STATUSES.forEach((status) => {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = ORDER_STATUS_LABELS[status] || status;
    if (status === order.status) option.selected = true;
    select.appendChild(option);
  });

  const updateBtn = document.createElement("button");
  updateBtn.type = "button";
  updateBtn.className = "btn btn-primary btn-small";
  updateBtn.textContent = "Update Status";

  const statusError = document.createElement("p");
  statusError.className = "admin-state admin-state--error is-hidden";
  statusError.setAttribute("role", "alert");

  updateBtn.addEventListener("click", async () => {
    updateBtn.disabled = true;
    statusError.classList.add("is-hidden");
    statusError.textContent = "";

    try {
      const result = await updateOrderStatus(order.id, select.value);
      // re-render the drawer with fresh data, carrying the just-created (or
      // reused) draft's id through so the Customer Update section can link
      // straight to it -- see buildCustomerUpdateSection.
      await openOrderDrawer(order.id, { justUpdatedNotificationId: result.notificationId });
      loadOrders(); // refresh the table/pagination behind it
    } catch (error) {
      statusError.textContent = error.message || "Unable to update status.";
      statusError.classList.remove("is-hidden");
    } finally {
      updateBtn.disabled = false;
    }
  });

  controls.append(select, updateBtn);
  section.append(controls, statusError);
  return section;
}

async function openOrderDrawer(orderId, { justUpdatedNotificationId = null } = {}) {
  const backdrop = document.getElementById("orderDrawerBackdrop");
  const drawer = document.getElementById("orderDrawer");
  const body = document.getElementById("orderDrawerBody");

  backdrop.classList.remove("is-hidden");
  drawer.classList.remove("is-hidden");
  drawer.setAttribute("aria-hidden", "false");
  renderLoadingState(body, "Loading order…");

  setOrdersStateInUrl({ ...getOrdersStateFromUrl(), id: orderId }, { replace: true });

  try {
    const order = await getAdminOrder(orderId);
    renderOrderDetail(order, { justUpdatedNotificationId });
  } catch (error) {
    renderErrorState(body, "Unable to load this order.");
  }
}

function closeOrderDrawer() {
  document.getElementById("orderDrawerBackdrop").classList.add("is-hidden");
  const drawer = document.getElementById("orderDrawer");
  drawer.classList.add("is-hidden");
  drawer.setAttribute("aria-hidden", "true");

  setOrdersStateInUrl({ ...getOrdersStateFromUrl(), id: null }, { replace: true });
}

function initDrawerCloseHandlers() {
  document.getElementById("orderDrawerClose").addEventListener("click", closeOrderDrawer);
  document.getElementById("orderDrawerBackdrop").addEventListener("click", closeOrderDrawer);
}

document.addEventListener("DOMContentLoaded", () => {
  loadOrders();
  initFilterForm();
  initPaginationButtons();
  initDrawerCloseHandlers();

  const state = getOrdersStateFromUrl();
  if (state.id) {
    openOrderDrawer(state.id);
  }
});
