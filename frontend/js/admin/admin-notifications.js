// CakeCraft Studio Backoffice — Notification Queue page: filter by status,
// paginate, and drive the approval workflow from a detail drawer (same
// open/close/backdrop pattern as admin-orders.js's order drawer, reused
// rather than reinvented). Status filter state lives in the URL query
// string, same convention as every other admin list page.
//
// Render functions build DOM via createElement + textContent, not
// innerHTML + interpolation — the notification body itself is rendered
// from a template today (see backend/app/services/notification_templates.py)
// but is *editable* by staff (the whole point of the approval workflow is
// a human can rewrite it before it goes out), so by the time this page
// displays it, it's staff-authored free text — the same trust boundary as
// customer-submitted fields elsewhere in this admin app.

const NOTIFICATIONS_PAGE_SIZE = 20;
const ALL_NOTIFICATION_STATUSES = [
  "queued",
  "draft",
  "awaiting_approval",
  "approved",
  "sent",
];

function getNotificationsStateFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return {
    status: params.get("status") || "",
    page: Number(params.get("page")) || 1,
    id: params.get("id") || null,
  };
}

function setNotificationsStateInUrl(state, { replace = false } = {}) {
  const params = new URLSearchParams();
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

function truncate(text, maxLength) {
  if (!text) return "—";
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
}

// --- Queue table -------------------------------------------------------

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
    "<tr><th>Customer</th><th>Event</th><th>Status</th><th>Preview</th><th>Created</th></tr>";
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  notifications.forEach((notification) => {
    const tr = document.createElement("tr");
    tr.className = "admin-table__row--clickable";
    tr.tabIndex = 0;

    const customerCell = document.createElement("td");
    customerCell.textContent = notification.customers ? notification.customers.name : "—";

    const eventCell = document.createElement("td");
    eventCell.textContent = NOTIFICATION_EVENT_LABELS[notification.event] || notification.event;

    const statusCell = document.createElement("td");
    statusCell.appendChild(renderNotificationStatusBadge(notification.status));

    const previewCell = document.createElement("td");
    previewCell.className = "admin-table__preview-cell";
    previewCell.textContent = truncate(notification.subject, 60);

    const createdCell = document.createElement("td");
    createdCell.textContent = formatDateTime(notification.created_at);

    tr.append(customerCell, eventCell, statusCell, previewCell, createdCell);

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

  document.getElementById("notificationsStatusFilter").value = state.status;

  try {
    const result = await getAdminNotifications({
      status: state.status || undefined,
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
    const status = document.getElementById("notificationsStatusFilter").value;
    setNotificationsStateInUrl({ status, page: 1 });
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

function buildActionBar(notification, { sendError } = {}) {
  const bar = document.createElement("div");
  bar.className = "notification-actions";

  const errorEl = document.createElement("p");
  errorEl.className = "admin-state admin-state--error is-hidden";
  errorEl.setAttribute("role", "alert");
  if (sendError) {
    errorEl.textContent = `Send failed: ${sendError}`;
    errorEl.classList.remove("is-hidden");
  }

  const runAction = async (actionFn) => {
    errorEl.classList.add("is-hidden");
    try {
      const result = await actionFn(notification.id);
      // send() reports a real delivery failure as a 200 with
      // status: "failed" (never sent, never thrown, never retried
      // automatically -- see notification_service.send()), not an HTTP
      // error, so it needs checking directly: the adapter's error text
      // only exists on this direct response, not on a later GET, so a
      // plain drawer refresh would lose it.
      if (result && result.status === "failed" && result.error) {
        renderNotificationDetail(result, { sendError: result.error });
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
  // submit-for-approval/approve step (removed -- it only added clicks at
  // this project's current stage, not a real second decision-maker); the
  // one safety principle that step existed for is unchanged, a draft is
  // never sent automatically, this button is the one human click that
  // ever triggers send(). "failed" gets the exact same action -- retry is
  // just clicking Send again, no extra step to get back to draft first.
  // awaiting_approval/approved stay sendable too (see
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

function renderNotificationDetail(notification, { sendError } = {}) {
  const body = document.getElementById("notificationDrawerBody");
  body.innerHTML = "";

  appendDetailRow(body, "Customer", notification.customers ? notification.customers.name : "—");
  appendDetailRow(body, "Email", notification.customers ? notification.customers.email : "—");
  appendDetailRow(
    body,
    "Event",
    NOTIFICATION_EVENT_LABELS[notification.event] || notification.event
  );
  appendDetailRow(body, "Created", formatDateTime(notification.created_at));

  const statusRow = document.createElement("div");
  statusRow.className = "admin-detail-row";
  const statusLabel = document.createElement("span");
  statusLabel.className = "admin-detail-row__label";
  statusLabel.textContent = "Status";
  statusRow.append(statusLabel, renderNotificationStatusBadge(notification.status));
  body.appendChild(statusRow);

  // Only present once a real adapter (Gmail, as of Sprint 3) has actually
  // attempted delivery — null/absent for anything still queued/draft/
  // awaiting_approval/approved, and for every notification the seeder
  // creates while no adapter is configured (see notification_service._dispatch).
  if (notification.channel) {
    appendDetailRow(body, "Channel", notification.channel);
  }
  if (notification.provider_message_id) {
    appendDetailRow(body, "Provider Message ID", notification.provider_message_id);
  }

  const previewHeading = document.createElement("h3");
  previewHeading.className = "admin-drawer__section-heading";
  previewHeading.textContent = "Preview";
  body.appendChild(previewHeading);
  body.appendChild(
    buildPreviewBlock(notification, { editable: notification.status === "draft" || notification.status === "failed" })
  );

  const actionsHeading = document.createElement("h3");
  actionsHeading.className = "admin-drawer__section-heading";
  actionsHeading.textContent = "Actions";
  body.appendChild(actionsHeading);
  body.appendChild(buildActionBar(notification, { sendError }));
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
    const notification = await getAdminNotification(notificationId);
    renderNotificationDetail(notification);
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

document.addEventListener("DOMContentLoaded", () => {
  loadNotifications();
  initFilterForm();
  initPaginationButtons();
  initDrawerCloseHandlers();

  const state = getNotificationsStateFromUrl();
  if (state.id) {
    openNotificationDrawer(state.id);
  }
});
