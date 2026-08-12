// CakeCraft Studio Backoffice — Communications workspace: the user-facing
// name for what's still the Notification Queue underneath (same table,
// same API — see backend/app/api/routes/admin/notifications.py). Simple
// workflow: draft -> Send -> sent/failed, a human always clicks Send,
// nothing goes out automatically. Filter by view/channel/source,
// paginate, and drive that workflow from a detail drawer (same
// open/close/backdrop pattern as admin-orders.js's order drawer, reused
// rather than reinvented). Filter state lives in the URL query string,
// same convention as every other admin list page.
//
// Render functions build DOM via createElement + textContent, not
// innerHTML + interpolation — the notification body itself is rendered
// from a template today (see backend/app/services/notification_templates.py)
// but is *editable* by staff before it's sent, so by the time this page
// displays it, it's staff-authored free text — the same trust boundary as
// customer-submitted fields elsewhere in this admin app.

const NOTIFICATIONS_PAGE_SIZE = 20;

// "Needs Review" is the default landing view — what a staff member opening
// Communications should see first is what needs their attention, not an
// unfiltered firehose (mirrors admin/notifications.py's VIEW_STATUSES).
const DEFAULT_NOTIFICATIONS_VIEW = "needs_review";

function getNotificationsStateFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return {
    view: params.get("view") || DEFAULT_NOTIFICATIONS_VIEW,
    channel: params.get("channel") || "",
    source: params.get("source") || "",
    page: Number(params.get("page")) || 1,
    id: params.get("id") || null,
  };
}

function setNotificationsStateInUrl(state, { replace = false } = {}) {
  const params = new URLSearchParams();
  if (state.view && state.view !== DEFAULT_NOTIFICATIONS_VIEW) params.set("view", state.view);
  if (state.channel) params.set("channel", state.channel);
  if (state.source) params.set("source", state.source);
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

function truncate(text, maxLength) {
  if (!text) return "—";
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
}

// --- Queue table -------------------------------------------------------

// Step 3B's intent/handling/review_reason/knowledge_sources arrive via a
// reverse embed (see backend/app/services/notification_service.py's
// _NOTIFICATION_SELECT) -- PostgREST always returns that as a list, at
// most one entry by construction; every call site just wants "the one
// entry, or none for a non-inbound-drafted notification".
function getNotificationIntelligence(notification) {
  return (notification.inbound_messages && notification.inbound_messages[0]) || null;
}

function renderNotificationsTable(notifications) {
  const container = document.getElementById("notificationsTableContainer");
  container.innerHTML = "";

  if (notifications.length === 0) {
    renderEmptyState(container, "No notifications match this filter.");
    return;
  }

  const table = document.createElement("table");
  table.className = "admin-table";

  const thead = document.createElement("thead");
  thead.innerHTML =
    "<tr><th>Customer</th><th>Channel</th><th>Event</th><th>Intent</th><th>Handling</th><th>Status</th><th>Preview</th><th>Created</th></tr>";
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  notifications.forEach((notification) => {
    const tr = document.createElement("tr");
    tr.className = "admin-table__row--clickable";
    tr.tabIndex = 0;

    const intelligence = getNotificationIntelligence(notification);

    const customerCell = document.createElement("td");
    customerCell.textContent = notification.customers ? notification.customers.name : "—";

    const channelCell = document.createElement("td");
    channelCell.appendChild(renderChannelBadge(notification.channel));

    const eventCell = document.createElement("td");
    eventCell.append(
      document.createTextNode(NOTIFICATION_EVENT_LABELS[notification.event] || notification.event),
      document.createElement("br"),
      renderSourceBadge(notification.event)
    );

    const intentCell = document.createElement("td");
    intentCell.textContent = intelligence && intelligence.intent ? (INTENT_LABELS[intelligence.intent] || intelligence.intent) : "—";

    const handlingCell = document.createElement("td");
    if (intelligence && intelligence.handling) {
      handlingCell.appendChild(renderHandlingBadge(intelligence.handling));
    } else {
      handlingCell.textContent = "—";
    }

    const statusCell = document.createElement("td");
    statusCell.appendChild(renderNotificationStatusBadge(notification.status));

    const previewCell = document.createElement("td");
    previewCell.className = "admin-table__preview-cell";
    previewCell.textContent = truncate(notification.subject, 60);

    const createdCell = document.createElement("td");
    createdCell.textContent = formatDateTime(notification.created_at);

    tr.append(customerCell, channelCell, eventCell, intentCell, handlingCell, statusCell, previewCell, createdCell);

    const open = () => openNotificationDrawer(notification.id);
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
  document.getElementById("notificationsPageInfo").textContent =
    `Page ${page} of ${totalPages} (${total} notification${total === 1 ? "" : "s"})`;

  document.getElementById("notificationsPrevPage").disabled = page <= 1;
  document.getElementById("notificationsNextPage").disabled = page >= totalPages;
}

async function loadNotifications() {
  const state = getNotificationsStateFromUrl();
  const container = document.getElementById("notificationsTableContainer");
  renderLoadingState(container, "Loading notifications…");

  document.getElementById("notificationsViewFilter").value = state.view;
  document.getElementById("notificationsChannelFilter").value = state.channel;
  document.getElementById("notificationsSourceFilter").value = state.source;

  try {
    const result = await getAdminNotifications({
      view: state.view,
      channel: state.channel || undefined,
      source: state.source || undefined,
      page: state.page,
      pageSize: NOTIFICATIONS_PAGE_SIZE,
    });
    renderNotificationsTable(result.items);
    renderPagination(result.total, result.page, result.pageSize);
  } catch (error) {
    renderErrorState(container, "Unable to load notifications. Please try again.");
  }
}

function initFilterForm() {
  const form = document.getElementById("notificationsFilterForm");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const view = document.getElementById("notificationsViewFilter").value;
    const channel = document.getElementById("notificationsChannelFilter").value;
    const source = document.getElementById("notificationsSourceFilter").value;
    setNotificationsStateInUrl({ view, channel, source, page: 1 });
    loadNotifications();
  });
}

function initPaginationButtons() {
  document.getElementById("notificationsPrevPage").addEventListener("click", () => {
    const state = getNotificationsStateFromUrl();
    if (state.page > 1) {
      setNotificationsStateInUrl({ ...state, page: state.page - 1 });
      loadNotifications();
    }
  });

  document.getElementById("notificationsNextPage").addEventListener("click", () => {
    const state = getNotificationsStateFromUrl();
    setNotificationsStateInUrl({ ...state, page: state.page + 1 });
    loadNotifications();
  });
}

// --- Detail drawer: preview + approval workflow ----------------------------

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

function isCurrentAdminRole(role) {
  const session = getAdminSession();
  return !!session && session.user && session.user.role === role;
}

function buildPreviewBlock(notification, { editable }) {
  const wrap = document.createElement("div");
  wrap.className = "notification-preview";

  if (!editable) {
    const subjectEl = document.createElement("p");
    subjectEl.className = "notification-preview__subject";
    subjectEl.textContent = notification.subject || "(no subject)";

    const bodyEl = document.createElement("p");
    bodyEl.className = "notification-preview__body";
    bodyEl.textContent = notification.body || "(no content yet)";

    wrap.append(subjectEl, bodyEl);
    return wrap;
  }

  const subjectInput = document.createElement("input");
  subjectInput.type = "text";
  subjectInput.id = "notificationSubjectInput";
  subjectInput.setAttribute("aria-label", "Subject");
  subjectInput.value = notification.subject || "";

  const bodyTextarea = document.createElement("textarea");
  bodyTextarea.id = "notificationBodyInput";
  bodyTextarea.setAttribute("aria-label", "Message");
  bodyTextarea.rows = 5;
  bodyTextarea.value = notification.body || "";

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "btn btn-small";
  saveBtn.textContent = "Save Changes";

  const saveError = document.createElement("p");
  saveError.className = "admin-state admin-state--error is-hidden";
  saveError.setAttribute("role", "alert");

  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    saveError.classList.add("is-hidden");
    try {
      await updateNotificationContent(notification.id, subjectInput.value, bodyTextarea.value);
      await openNotificationDrawer(notification.id);
    } catch (error) {
      saveError.textContent = error.message || "Unable to save changes.";
      saveError.classList.remove("is-hidden");
    } finally {
      saveBtn.disabled = false;
    }
  });

  wrap.append(subjectInput, bodyTextarea, saveBtn, saveError);
  return wrap;
}

function buildActionBar(notification) {
  const bar = document.createElement("div");
  bar.className = "notification-actions";

  const errorEl = document.createElement("p");
  errorEl.className = "admin-state admin-state--error is-hidden";
  errorEl.setAttribute("role", "alert");

  const runAction = async (actionFn) => {
    errorEl.classList.add("is-hidden");
    try {
      const result = await actionFn(notification.id);
      // send() reports a real delivery failure as a 200 with
      // status: "failed" (never sent, never a thrown error, never
      // retried automatically — see notification_service.send()), not an
      // HTTP error, so this is the one place that result needs
      // inspecting directly rather than just refreshing the drawer: the
      // adapter's error text (result.error) only exists on this direct
      // response, not on a later GET, so it has to be shown from here.
      if (result && result.status === "failed" && result.error) {
        const sourceMessage = await getNotificationSourceMessage(notification.id).catch(() => null);
        renderNotificationDetail(result, sourceMessage);
        loadNotifications();
        return;
      }
      await openNotificationDrawer(notification.id);
      loadNotifications();
    } catch (error) {
      errorEl.textContent = error.message || "Unable to complete this action.";
      errorEl.classList.remove("is-hidden");
    }
  };

  const addButton = (label, onClick, { primary = false } = {}) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = primary ? "btn btn-primary btn-small" : "btn btn-small";
    btn.textContent = label;
    btn.addEventListener("click", () => runAction(onClick));
    bar.appendChild(btn);
  };

  // Simplified workflow: draft -> Send -> sent/failed. No separate
  // submit-for-approval/approve step (removed — it only added clicks at
  // this project's current stage, not a real second decision-maker); the
  // one safety principle that step existed for is unchanged, a draft is
  // never sent automatically, this button is the one human click that
  // ever triggers send(). "failed" gets the exact same button — retry is
  // just clicking Send again, no extra step to get back to draft first.
  // awaiting_approval/approved are kept sendable too (see
  // notification_service._SEND_ALLOWED_FROM) purely so nothing created by
  // the old workflow, before this change, is ever stuck with no action.
  if (["draft", "awaiting_approval", "approved", "failed"].includes(notification.status)) {
    addButton(notification.status === "failed" ? "Retry Send" : "Send", sendNotification, { primary: true });
  }

  if (bar.children.length === 0) {
    const note = document.createElement("p");
    note.className = "admin-state";
    note.textContent =
      notification.status === "sent"
        ? `Sent ${formatDateTime(notification.sent_at)}.`
        : "This notification is still being prepared.";
    bar.appendChild(note);
  }

  bar.appendChild(errorEl);
  return bar;
}

// sourceMessage is the inbound customer message this draft was created
// from (Step 3), or null for every notification created by the other
// paths (an order-status change, or a staff-initiated on-demand draft) --
// most notifications, not an error. Fetched alongside the notification
// itself in openNotificationDrawer, not inside this function, so this
// stays a plain synchronous render like every other call site expects.
function renderNotificationDetail(notification, sourceMessage) {
  const body = document.getElementById("notificationDrawerBody");
  body.innerHTML = "";

  const intelligence = getNotificationIntelligence(notification);

  appendDetailRow(body, "Customer", notification.customers ? notification.customers.name : "—");
  appendDetailRow(body, "Email", notification.customers ? notification.customers.email : "—");
  appendDetailRow(
    body,
    "Event",
    NOTIFICATION_EVENT_LABELS[notification.event] || notification.event
  );

  // Step 3B "Order context" — the minimum a reviewer needs (which cake,
  // current status, when it's due), only shown when this draft is
  // actually tied to one (order_id is nullable — see the Step 3
  // migration; a general/prospective question has none).
  if (notification.orders) {
    const template = notification.orders.cake_templates;
    const orderSummary = template ? `${template.name} (${template.category}) — ${notification.orders.status}` : notification.orders.status;
    appendDetailRow(body, "Order", orderSummary);
  }

  appendDetailRow(body, "Created", formatDateTime(notification.created_at));

  const statusRow = document.createElement("div");
  statusRow.className = "admin-detail-row";
  const statusLabel = document.createElement("span");
  statusLabel.className = "admin-detail-row__label";
  statusLabel.textContent = "Status";
  statusRow.append(statusLabel, renderNotificationStatusBadge(notification.status));
  body.appendChild(statusRow);

  // Only present on the direct response to a /send call that just failed
  // (see buildActionBar's runAction) — a real delivery error (bad
  // recipient, SMTP failure, etc.), not persisted, so it's shown once,
  // right when it's most actionable, and won't reappear on a later
  // reload of this same notification (status alone still shows "Failed").
  if (notification.status === "failed" && notification.error) {
    const errorCallout = document.createElement("div");
    errorCallout.className = "admin-review-callout";
    const title = document.createElement("p");
    title.className = "admin-review-callout__title";
    title.textContent = "Send failed";
    const reason = document.createElement("p");
    reason.textContent = notification.error;
    errorCallout.append(title, reason);
    body.appendChild(errorCallout);
  }

  // Every notification has a channel from creation now (Communications
  // Workspace, Step 2 — see notification_service._insert_queued /
  // agent_service.draft_customer_communication), so this is always shown,
  // not just once a real adapter has actually attempted delivery. Falls
  // back to "email" only for notifications created before this change
  // (channel is nullable in the DB, still) — matching _dispatch()'s own
  // DEFAULT_CHANNEL resolution, so the displayed value always matches
  // what would actually be used if sent.
  appendDetailRow(body, "Channel", CHANNEL_LABELS[notification.channel] || CHANNEL_LABELS.email);
  if (notification.provider_message_id) {
    appendDetailRow(body, "Provider Message ID", notification.provider_message_id);
  }

  // Step 3B: intent + handling — only present for a notification that
  // came from an inbound message (see getNotificationIntelligence).
  // handling is the application's own risk decision, never Claude's
  // (see agent_service._compute_handling) — shown here exactly as
  // computed, not re-derived client-side.
  if (intelligence && intelligence.intent) {
    appendDetailRow(body, "Intent", INTENT_LABELS[intelligence.intent] || intelligence.intent);
  }
  if (intelligence && intelligence.handling) {
    const handlingRow = document.createElement("div");
    handlingRow.className = "admin-detail-row";
    const handlingLabel = document.createElement("span");
    handlingLabel.className = "admin-detail-row__label";
    handlingLabel.textContent = "Handling";
    handlingRow.append(handlingLabel, renderHandlingBadge(intelligence.handling));
    body.appendChild(handlingRow);
  }

  // Step 3B "human review required" explanation — why the AI didn't (or
  // couldn't) confidently answer on its own, not just a bare status.
  if (intelligence && intelligence.handling && intelligence.handling !== "green" && intelligence.review_reason) {
    const callout = document.createElement("div");
    callout.className = "admin-review-callout";
    const title = document.createElement("p");
    title.className = "admin-review-callout__title";
    title.textContent = "Human review required";
    const reason = document.createElement("p");
    reason.textContent = intelligence.review_reason;
    callout.append(title, reason);
    body.appendChild(callout);
  }

  // Step 3: the customer's own message, shown above the AI's draft reply
  // when this notification came from an inbound conversation — same
  // section-heading/preview-block visual language as the rest of the
  // drawer, not a new component.
  if (sourceMessage) {
    const sourceHeading = document.createElement("h3");
    sourceHeading.className = "admin-drawer__section-heading";
    sourceHeading.textContent = "Customer Message";
    body.appendChild(sourceHeading);

    const sourceWrap = document.createElement("div");
    sourceWrap.className = "notification-preview";
    const sourceMeta = document.createElement("p");
    sourceMeta.className = "notification-preview__subject";
    sourceMeta.textContent = `Via ${CHANNEL_LABELS[sourceMessage.channel] || sourceMessage.channel}${sourceMessage.subject ? ` — ${sourceMessage.subject}` : ""}`;
    const sourceBody = document.createElement("p");
    sourceBody.className = "notification-preview__body";
    sourceBody.textContent = sourceMessage.body;
    sourceWrap.append(sourceMeta, sourceBody);
    body.appendChild(sourceWrap);
  }

  const previewHeading = document.createElement("h3");
  previewHeading.className = "admin-drawer__section-heading";
  previewHeading.textContent = sourceMessage ? "AI Draft Reply" : "Preview";
  body.appendChild(previewHeading);

  // Step 3B "Knowledge used" — a concise indication of which trusted
  // CakeCraft documents grounded the draft, not raw embeddings/technical
  // detail (see agent_service.draft_reply_to_inbound_message's
  // knowledge_sources — just title/sourceFile, the same shape the AI
  // Agent's other RAG-grounded surfaces already show).
  if (intelligence && intelligence.knowledge_sources && intelligence.knowledge_sources.length > 0) {
    const knowledgeP = document.createElement("p");
    knowledgeP.className = "admin-knowledge-used";
    knowledgeP.textContent = `Knowledge used: ${intelligence.knowledge_sources.map((s) => s.title).join(", ")}`;
    body.appendChild(knowledgeP);
  }

  body.appendChild(
    buildPreviewBlock(notification, { editable: notification.status === "draft" || notification.status === "failed" })
  );

  const actionsHeading = document.createElement("h3");
  actionsHeading.className = "admin-drawer__section-heading";
  actionsHeading.textContent = "Actions";
  body.appendChild(actionsHeading);
  body.appendChild(buildActionBar(notification));
}

async function openNotificationDrawer(notificationId) {
  const backdrop = document.getElementById("notificationDrawerBackdrop");
  const drawer = document.getElementById("notificationDrawer");
  const body = document.getElementById("notificationDrawerBody");

  backdrop.classList.remove("is-hidden");
  drawer.classList.remove("is-hidden");
  drawer.setAttribute("aria-hidden", "false");
  renderLoadingState(body, "Loading notification…");

  setNotificationsStateInUrl({ ...getNotificationsStateFromUrl(), id: notificationId }, { replace: true });

  try {
    const [notification, sourceMessage] = await Promise.all([
      getAdminNotification(notificationId),
      // A missing source message is the common, valid case (see
      // renderNotificationDetail) -- never let that failure mode block
      // the drawer from showing the notification itself.
      getNotificationSourceMessage(notificationId).catch(() => null),
    ]);
    renderNotificationDetail(notification, sourceMessage);
  } catch (error) {
    renderErrorState(body, "Unable to load this notification.");
  }
}

function closeNotificationDrawer() {
  document.getElementById("notificationDrawerBackdrop").classList.add("is-hidden");
  const drawer = document.getElementById("notificationDrawer");
  drawer.classList.add("is-hidden");
  drawer.setAttribute("aria-hidden", "true");

  setNotificationsStateInUrl({ ...getNotificationsStateFromUrl(), id: null }, { replace: true });
}

function initDrawerCloseHandlers() {
  document.getElementById("notificationDrawerClose").addEventListener("click", closeNotificationDrawer);
  document.getElementById("notificationDrawerBackdrop").addEventListener("click", closeNotificationDrawer);
}

// --- Inbox: inbound messages with no resulting draft yet (Step 3) ----------
// A message that *did* get drafted already shows up as that draft in the
// regular list above — this is deliberately not a second, parallel view
// of everything, only what still needs a human's attention as a raw
// inbound message (unrecognized sender, or the AI Agent couldn't process
// it). Hidden entirely when empty, the common case, so the workspace
// doesn't stay cluttered with an empty panel.

function renderInboxTable(items) {
  const container = document.getElementById("inboxContainer");
  container.innerHTML = "";

  const table = document.createElement("table");
  table.className = "admin-table";

  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>Sender</th><th>Channel</th><th>Preview</th><th>Status</th><th>Received</th></tr>";
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  items.forEach((item) => {
    const tr = document.createElement("tr");

    const senderCell = document.createElement("td");
    senderCell.textContent = item.customers ? item.customers.name : `${item.sender_identifier} (unrecognized)`;

    const channelCell = document.createElement("td");
    channelCell.appendChild(renderChannelBadge(item.channel));

    const previewCell = document.createElement("td");
    previewCell.className = "admin-table__preview-cell";
    previewCell.textContent = truncate(item.body, 60);

    const statusCell = document.createElement("td");
    statusCell.textContent = INBOUND_AI_STATUS_LABELS[item.ai_status] || item.ai_status;

    const receivedCell = document.createElement("td");
    receivedCell.textContent = formatDateTime(item.received_at);

    tr.append(senderCell, channelCell, previewCell, statusCell, receivedCell);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);
}

async function loadInbox() {
  const section = document.getElementById("inboxSection");
  const container = document.getElementById("inboxContainer");
  section.classList.remove("is-hidden");
  renderLoadingState(container, "Checking inbox…");

  try {
    const result = await getCommunicationsInbox();
    if (result.items.length === 0) {
      section.classList.add("is-hidden");
      return;
    }
    renderInboxTable(result.items);
  } catch (error) {
    renderErrorState(container, "Unable to load the inbox.");
  }
}

function initCheckEmailButton() {
  const btn = document.getElementById("checkEmailBtn");
  const originalLabel = btn.textContent;

  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Checking…";
    try {
      const result = await checkForNewEmail();
      btn.textContent = result.checked > 0 ? `Found ${result.checked} new` : "No new messages";
      await loadInbox();
      await loadNotifications();
    } catch (error) {
      btn.textContent = "Check failed";
    } finally {
      setTimeout(() => {
        btn.textContent = originalLabel;
        btn.disabled = false;
      }, 2500);
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  loadNotifications();
  loadInbox();
  initFilterForm();
  initPaginationButtons();
  initDrawerCloseHandlers();
  initCheckEmailButton();

  const state = getNotificationsStateFromUrl();
  if (state.id) {
    openNotificationDrawer(state.id);
  }
});
