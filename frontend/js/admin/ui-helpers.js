// CakeCraft Studio Backoffice — shared render helpers: status badges and
// the loading/error/empty states every admin page needs. Centralized here
// so all four look and behave identically everywhere instead of being
// reimplemented per page (and so nothing has to hand-build HTML strings
// out of server data — see renderStatusBadge, which builds a real element
// via textContent rather than string interpolation).

const ORDER_STATUS_LABELS = {
  pending: "Pending",
  confirmed: "Confirmed",
  in_progress: "In Progress",
  ready: "Ready",
  completed: "Completed",
  cancelled: "Cancelled",
};

function renderStatusBadge(status) {
  const span = document.createElement("span");
  span.className = `status-badge status-badge--${status}`;
  span.textContent = ORDER_STATUS_LABELS[status] || status;
  return span;
}

// Mirrors backend/app/services/notification_templates.py's EVENT_LABELS —
// duplicated here (not fetched) because it's presentation-only, static
// data with no reason to round-trip the network for; if the backend adds
// a template this list doesn't know about yet, notification event names
// still render (falling back to the raw key, same as ORDER_STATUS_LABELS
// already does for an unrecognized order status).
const NOTIFICATION_EVENT_LABELS = {
  order_confirmed: "Order Confirmed",
  baking_started: "Baking Started",
  ready_for_pickup: "Ready for Pickup",
  order_completed: "Completed",
  order_cancelled: "Order Cancelled",
};

const NOTIFICATION_STATUS_LABELS = {
  queued: "Queued",
  draft: "Draft",
  awaiting_approval: "Awaiting Approval",
  approved: "Approved",
  sent: "Sent",
  delivered: "Delivered",
  failed: "Failed",
};

// Reuses the same .status-badge component renderStatusBadge already
// defines — just a different label lookup and modifier-class namespace
// (status-badge--notification-*) so notification statuses (draft,
// awaiting_approval, ...) never collide with order statuses that happen
// to share a word in spirit but not in styling.
function renderNotificationStatusBadge(status) {
  const span = document.createElement("span");
  span.className = `status-badge status-badge--notification-${status}`;
  span.textContent = NOTIFICATION_STATUS_LABELS[status] || status;
  return span;
}

function renderLoadingState(container, message = "Loading…") {
  container.innerHTML = "";
  const p = document.createElement("p");
  p.className = "admin-state admin-state--loading";
  p.textContent = message;
  container.appendChild(p);
}

function renderErrorState(container, message = "Something went wrong. Please try again.") {
  container.innerHTML = "";
  const p = document.createElement("p");
  p.className = "admin-state admin-state--error";
  p.textContent = message;
  container.appendChild(p);
}

function renderEmptyState(container, message = "Nothing here yet.") {
  container.innerHTML = "";
  const p = document.createElement("p");
  p.className = "admin-state admin-state--empty";
  p.textContent = message;
  container.appendChild(p);
}

// Distinct from renderEmptyState on purpose: "empty" means the feature is
// live but has no data yet; "placeholder" means the feature itself isn't
// enabled yet (Communications, AI Insights — see docs/EPIC1_CUSTOMERS.md).
// Visually extends the dashed-border treatment the Dashboard's AI Insights
// card already established, rather than inventing a new look for the same
// idea.
function renderPlaceholderState(container, message = "Coming in a future phase.") {
  container.innerHTML = "";
  const p = document.createElement("p");
  p.className = "admin-state admin-state--placeholder";
  p.textContent = message;
  container.appendChild(p);
}

function formatCurrency(amount) {
  return `$${Number(amount).toFixed(2)}`;
}

function formatDateTime(isoString) {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
