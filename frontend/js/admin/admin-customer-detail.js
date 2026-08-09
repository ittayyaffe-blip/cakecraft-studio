// CakeCraft Studio Backoffice — Customer profile page. Reads ?id= from the
// URL and loads five independent panels (profile header, order history,
// timeline, communications, AI insights) — each fetches and renders on
// its own, so a slow/failed panel never blocks the others.
//
// Order rows link to admin-orders.html?id=<orderId> rather than
// re-rendering order detail here — that page already owns full order
// detail + status update; this page reuses it instead of duplicating it.
//
// Render functions build DOM via createElement + textContent, not
// innerHTML + interpolation, for the same reason as every other admin
// page: customer name/email/phone/notes originate from the public,
// unauthenticated order form.

function getCustomerIdFromUrl() {
  return new URLSearchParams(window.location.search).get("id");
}

function renderProfileHeader(customer) {
  document.getElementById("customerName").textContent = customer.name;

  const fields = [
    ["Email", customer.email],
    ["Phone", customer.phone || "—"],
    ["Customer Since", formatDateTime(customer.created_at)],
    ["Total Orders", String(customer.orderCount)],
    ["Lifetime Value", formatCurrency(customer.lifetimeValue)],
    ["Last Order", formatDateTime(customer.lastOrderDate)],
  ];

  const grid = document.getElementById("customerProfileGrid");
  grid.innerHTML = "";
  fields.forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "admin-health-item";

    const labelEl = document.createElement("span");
    labelEl.className = "admin-health-item__label";
    labelEl.textContent = label;

    const valueEl = document.createElement("span");
    valueEl.className = "admin-detail-row__value";
    valueEl.textContent = value;

    item.append(labelEl, valueEl);
    grid.appendChild(item);
  });
}

async function loadProfile(customerId) {
  try {
    const customer = await getAdminCustomer(customerId);
    renderProfileHeader(customer);
    return customer;
  } catch (error) {
    document.getElementById("customerName").textContent = "Unable to load this customer.";
    renderErrorState(document.getElementById("customerProfileGrid"), "Please try again.");
    return null;
  }
}

// --- Order history -----------------------------------------------------

function renderOrderHistory(orders) {
  const container = document.getElementById("customerOrdersContainer");
  container.innerHTML = "";

  if (orders.length === 0) {
    renderEmptyState(container, "No orders yet.");
    return;
  }

  const table = document.createElement("table");
  table.className = "admin-table";

  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>Cake</th><th>Status</th><th>Total</th><th>Placed</th></tr>";
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  orders.forEach((order) => {
    const tr = document.createElement("tr");
    tr.className = "admin-table__row--clickable";

    const cakeCell = document.createElement("td");
    cakeCell.textContent = order.cake_templates ? order.cake_templates.name : "—";

    const statusCell = document.createElement("td");
    statusCell.appendChild(renderStatusBadge(order.status));

    const totalCell = document.createElement("td");
    totalCell.textContent = formatCurrency(order.total_price);

    const placedCell = document.createElement("td");
    placedCell.textContent = formatDateTime(order.created_at);

    tr.append(cakeCell, statusCell, totalCell, placedCell);

    tr.tabIndex = 0;
    const open = () => {
      window.location.href = `admin-orders.html?id=${encodeURIComponent(order.id)}`;
    };
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

async function loadOrderHistory(customerId) {
  const container = document.getElementById("customerOrdersContainer");
  renderLoadingState(container, "Loading orders…");
  try {
    const orders = await getCustomerOrders(customerId);
    renderOrderHistory(orders);
  } catch (error) {
    renderErrorState(container, "Unable to load order history.");
  }
}

// --- Timeline ------------------------------------------------------------

function describeTimelineEvent(event) {
  if (event.type === "order_placed") {
    return `Placed an order — ${event.templateName || "cake"} (${ORDER_STATUS_LABELS[event.status] || event.status})`;
  }
  if (event.type === "order.status_changed") {
    const before = event.before && event.before.status ? event.before.status : "?";
    const after = event.after && event.after.status ? event.after.status : "?";
    return `Order status changed: ${before} → ${after} (by ${event.actorName || "System"})`;
  }
  if (event.type === "notification") {
    const statusLabel = NOTIFICATION_STATUS_LABELS[event.status] || event.status;
    return `Notification — ${event.label || event.type} (${statusLabel})`;
  }
  return event.type;
}

function renderTimeline(events) {
  const container = document.getElementById("customerTimelineContainer");
  container.innerHTML = "";

  if (events.length === 0) {
    renderEmptyState(container, "No activity yet.");
    return;
  }

  const list = document.createElement("ul");
  list.className = "admin-timeline";

  events.forEach((event) => {
    const li = document.createElement("li");
    li.className = "admin-timeline__item";

    const descriptionEl = document.createElement("span");
    descriptionEl.className = "admin-timeline__description";
    descriptionEl.textContent = describeTimelineEvent(event);

    const timeEl = document.createElement("span");
    timeEl.className = "admin-timeline__meta";
    timeEl.textContent = formatDateTime(event.timestamp);

    li.append(descriptionEl, timeEl);

    // Notification entries link through to the Notification Queue's own
    // detail drawer (Event-Driven Customer Communication Platform) —
    // reused, not re-rendered here, same as order rows link to
    // admin-orders.html above.
    if (event.type === "notification" && event.notificationId) {
      li.classList.add("admin-timeline__item--clickable");
      li.tabIndex = 0;
      const open = () => {
        window.location.href = `admin-notifications.html?id=${encodeURIComponent(event.notificationId)}`;
      };
      li.addEventListener("click", open);
      li.addEventListener("keydown", (keyEvent) => {
        if (keyEvent.key === "Enter" || keyEvent.key === " ") {
          keyEvent.preventDefault();
          open();
        }
      });
    }

    list.appendChild(li);
  });

  container.appendChild(list);
}

async function loadTimeline(customerId) {
  const container = document.getElementById("customerTimelineContainer");
  renderLoadingState(container, "Loading timeline…");
  try {
    const events = await getCustomerTimeline(customerId);
    renderTimeline(events);
  } catch (error) {
    renderErrorState(container, "Unable to load timeline.");
  }
}

// --- Placeholder panels: Communications, AI Insights ----------------------
// Both endpoints already return their real eventual shape
// (`{ enabled, items/insights }`) — see docs/EPIC1_CUSTOMERS.md. Today
// `enabled` is always false, so these two loaders always render the
// placeholder state; once Gmail/WhatsApp and the AI layer ship, the same
// loaders start rendering real content with no change here beyond that.

async function loadCommunications(customerId) {
  const container = document.getElementById("customerCommunicationsContainer");
  renderLoadingState(container, "Loading…");
  try {
    const result = await getCustomerCommunications(customerId);
    if (!result.enabled) {
      renderPlaceholderState(
        container,
        "Communications aren't enabled yet. Email and WhatsApp history will appear here in a future phase."
      );
      return;
    }
    if (result.items.length === 0) {
      renderEmptyState(container, "No messages sent yet.");
      return;
    }
    // Real rendering lands with the Communications phase itself.
  } catch (error) {
    renderErrorState(container, "Unable to load communications.");
  }
}

async function loadAIInsights(customerId) {
  const container = document.getElementById("customerAIInsightsContainer");
  renderLoadingState(container, "Loading…");
  try {
    const result = await getCustomerAIInsights(customerId);
    if (!result.enabled) {
      renderPlaceholderState(
        container,
        "AI Insights aren't enabled yet. Suggestions about this customer will appear here in a future phase."
      );
      return;
    }
    if (result.insights.length === 0) {
      renderEmptyState(container, "No insights yet.");
      return;
    }
    // Real rendering lands with the AI Operations Center phase itself.
  } catch (error) {
    renderErrorState(container, "Unable to load AI insights.");
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const customerId = getCustomerIdFromUrl();
  if (!customerId) {
    document.getElementById("customerName").textContent = "No customer specified.";
    return;
  }

  await loadProfile(customerId);
  loadOrderHistory(customerId);
  loadTimeline(customerId);
  loadCommunications(customerId);
  loadAIInsights(customerId);
});
