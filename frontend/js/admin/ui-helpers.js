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
  order_received: "Order Received",
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

// Step 3 — an inbound message's own processing status (distinct from a
// notification's status: this describes what the AI Agent did with the
// customer's message, not an outbound approval/delivery stage). Mirrors
// backend/app/services/inbound_service.py's ai_status values.
const INBOUND_AI_STATUS_LABELS = {
  pending: "Pending",
  processing: "Processing",
  drafted: "Drafted",
  unable_to_answer: "Unable to Answer",
  failed: "Needs Attention",
};

// Step 3B — Communication Intelligence & Guardrails. Mirrors backend/app/
// services/agent_service.py's INTENTS exactly (a human label per value,
// same closed set, nothing invented client-side).
const INTENT_LABELS = {
  PRODUCT_QUESTION: "Product Question",
  NEW_ORDER_INQUIRY: "New Order Inquiry",
  ORDER_STATUS: "Order Status",
  ORDER_CHANGE_REQUEST: "Order Change",
  PRICING: "Pricing",
  DISCOUNT_REQUEST: "Discount Request",
  REFUND_REQUEST: "Refund Request",
  DELIVERY: "Delivery",
  PICKUP: "Pickup",
  ALLERGY_DIETARY: "Allergy / Dietary",
  RELIGIOUS_DIETARY: "Religious Requirement",
  COMPLAINT: "Complaint",
  PRIVACY_REQUEST: "Privacy Request",
  LEGAL_THREAT: "Legal Threat",
  GENERAL_QUESTION: "General Question",
  HUMAN_REQUEST: "Human Requested",
  OTHER: "Other",
};

// handling is the application's own risk decision (never Claude's — see
// agent_service._compute_handling) — "AI Answer" for green (the AI could
// prepare a normal grounded response), "Human Review" for yellow/red (a
// business judgment call or a prohibited-autonomous-action category; the
// UI doesn't need to distinguish yellow from red beyond color, both mean
// "a human decides this, not the AI").
const HANDLING_LABELS = { green: "AI Answer", yellow: "Human Review", red: "Human Review" };

function renderHandlingBadge(handling) {
  const span = document.createElement("span");
  span.className = `status-badge status-badge--handling-${handling}`;
  span.textContent = HANDLING_LABELS[handling] || handling;
  return span;
}

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

// Communications Workspace (Step 2). channel is nullable only for
// notifications created before this feature (older rows never got a
// default) -- new ones always have one (see notification_service.
// _insert_queued / agent_service.draft_customer_communication) -- so this
// falls back to "email" (matching notification_service._dispatch's own
// DEFAULT_CHANNEL resolution) rather than showing nothing.
const CHANNEL_LABELS = { email: "Email", whatsapp: "WhatsApp" };

function renderChannelBadge(channel) {
  const resolved = channel || "email";
  const span = document.createElement("span");
  span.className = `status-badge status-badge--channel-${resolved}`;
  span.textContent = CHANNEL_LABELS[resolved] || resolved;
  return span;
}

// Source is derived from the existing `event` field, not a stored value:
// "agent_drafted" is the one event key the AI Agent's on-demand draft path
// uses (see agent_service.py); every other event key comes from an
// order-status transition's deterministic template, i.e. "automated" —
// mirrors backend/app/services/notification_service.py's VALID_SOURCES.
const SOURCE_LABELS = { automated: "Automated", ai_drafted: "AI-Drafted" };

function getNotificationSource(event) {
  return event === "agent_drafted" ? "ai_drafted" : "automated";
}

function renderSourceBadge(event) {
  const source = getNotificationSource(event);
  const span = document.createElement("span");
  span.className = `status-badge status-badge--source-${source}`;
  span.textContent = SOURCE_LABELS[source];
  return span;
}

// role="status"/"alert" goes on `container` — the pre-existing, page-defined
// element every caller passes in (e.g. #ragAskResult, #recentOrdersContainer)
// — not on the `<p>` created below. A freshly-inserted node that already
// carries aria-live/role is announced inconsistently across screen readers;
// a container that's already present and already marked as a live region
// reliably announces content replacing its children, which is exactly what
// container.innerHTML = "" + appendChild does here. It's also why this fix
// needs no other file: every caller in this codebase renders a loading
// state on a container before replacing it with real content or an error
// (grepped every call site to confirm), so marking the container once here
// covers that later, unrelated success-path render too — same container,
// same live region, no second role needed at the call site.
function renderLoadingState(container, message = "Loading…") {
  container.setAttribute("role", "status");
  container.innerHTML = "";
  const p = document.createElement("p");
  p.className = "admin-state admin-state--loading";
  p.textContent = message;
  container.appendChild(p);
}

function renderErrorState(container, message = "Something went wrong. Please try again.") {
  container.setAttribute("role", "alert");
  container.innerHTML = "";
  const p = document.createElement("p");
  p.className = "admin-state admin-state--error";
  p.textContent = message;
  container.appendChild(p);
}

function renderEmptyState(container, message = "Nothing here yet.") {
  container.setAttribute("role", "status");
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
  container.setAttribute("role", "status");
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
