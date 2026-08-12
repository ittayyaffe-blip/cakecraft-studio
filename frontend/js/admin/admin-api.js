// CakeCraft Studio Backoffice — API communication only. No rendering logic
// here, mirroring api.js's role on the customer side. Every admin fetch
// call goes through adminFetch() so the Authorization header and 401
// handling live in exactly one place instead of being repeated per page.
//
// Reuses API_BASE_URL from api.js — loaded before every admin/*.js file,
// so the constant is already in scope (classic scripts share one global
// scope; see the <script> order in each admin-*.html page).

async function adminFetch(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...getAuthHeader(),
      ...(options.headers || {}),
    },
  });

  if (response.status === 401) {
    clearAdminSession();
    window.location.href = "admin-login.html";
    throw new Error("Session expired");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed with status ${response.status}`);
  }

  return response.json();
}

async function adminLogin(email, password) {
  const response = await fetch(`${API_BASE_URL}/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Login failed");
  }

  return response.json();
}

async function adminLogout() {
  // Best-effort server-side revocation only — the caller always clears
  // local session state afterward regardless of whether this succeeds.
  await adminFetch("/admin/logout", { method: "POST" });
}

async function getAdminMe() {
  return adminFetch("/admin/me");
}

async function getDashboard() {
  return adminFetch("/admin/dashboard");
}

// --- AI Daily Briefing (Final AI Intelligence Phase) ------------------------

async function getDailyBriefing() {
  return adminFetch("/admin/briefing");
}

// --- Business Intelligence Layer: AI Operations Agent + RAG ----------------

async function getAgentMorningBriefing() {
  return adminFetch("/admin/agent/morning-briefing");
}

async function askAgent(question) {
  return adminFetch("/admin/agent/ask", { method: "POST", body: JSON.stringify({ question }) });
}

async function askRag(question) {
  return adminFetch("/admin/rag/ask", { method: "POST", body: JSON.stringify({ question }) });
}

async function draftAgentCommunication(orderId, instruction, channel) {
  return adminFetch("/admin/agent/draft-communication", {
    method: "POST",
    body: JSON.stringify({ orderId, instruction: instruction || null, channel: channel || null }),
  });
}

async function getAdminOrders({ search, status, page = 1, pageSize = 20 } = {}) {
  const query = new URLSearchParams();
  if (search) query.set("search", search);
  if (status) query.set("status", status);
  query.set("page", String(page));
  query.set("pageSize", String(pageSize));
  return adminFetch(`/admin/orders?${query.toString()}`);
}

async function getAdminOrder(orderId) {
  return adminFetch(`/admin/orders/${encodeURIComponent(orderId)}`);
}

async function updateOrderStatus(orderId, status) {
  return adminFetch(`/admin/orders/${encodeURIComponent(orderId)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

// --- Customers (Epic 1.2 — Customer Management & CRM) ----------------------

async function getAdminCustomers({ search, page = 1, pageSize = 20 } = {}) {
  const query = new URLSearchParams();
  if (search) query.set("search", search);
  query.set("page", String(page));
  query.set("pageSize", String(pageSize));
  return adminFetch(`/admin/customers?${query.toString()}`);
}

async function getAdminCustomer(customerId) {
  return adminFetch(`/admin/customers/${encodeURIComponent(customerId)}`);
}

async function getCustomerOrders(customerId) {
  return adminFetch(`/admin/customers/${encodeURIComponent(customerId)}/orders`);
}

async function getCustomerTimeline(customerId) {
  return adminFetch(`/admin/customers/${encodeURIComponent(customerId)}/timeline`);
}

// Both placeholder endpoints already return their real eventual shape
// (`{ enabled, items/insights }`) — see docs/EPIC1_CUSTOMERS.md. These two
// functions won't need to change when Communications/AI Insights ship,
// only the backend behind them will.
async function getCustomerCommunications(customerId) {
  return adminFetch(`/admin/customers/${encodeURIComponent(customerId)}/communications`);
}

async function getCustomerAIInsights(customerId) {
  return adminFetch(`/admin/customers/${encodeURIComponent(customerId)}/ai-insights`);
}

// --- Notifications (Event-Driven Customer Communication Platform) ---------

async function getAdminNotifications({ view, channel, source, page = 1, pageSize = 20 } = {}) {
  const query = new URLSearchParams();
  if (view) query.set("view", view);
  if (channel) query.set("channel", channel);
  if (source) query.set("source", source);
  query.set("page", String(page));
  query.set("pageSize", String(pageSize));
  return adminFetch(`/admin/notifications?${query.toString()}`);
}

async function getAdminNotification(notificationId) {
  return adminFetch(`/admin/notifications/${encodeURIComponent(notificationId)}`);
}

// The inbound customer message a draft was created from (Step 3) — null
// for every notification created by the other paths (order-status change,
// staff-initiated on-demand draft), not an error.
async function getNotificationSourceMessage(notificationId) {
  return adminFetch(`/admin/notifications/${encodeURIComponent(notificationId)}/source-message`);
}

async function updateNotificationContent(notificationId, subject, body) {
  return adminFetch(`/admin/notifications/${encodeURIComponent(notificationId)}`, {
    method: "PATCH",
    body: JSON.stringify({ subject, body }),
  });
}

async function submitNotification(notificationId) {
  return adminFetch(`/admin/notifications/${encodeURIComponent(notificationId)}/submit`, {
    method: "POST",
  });
}

// Admin-role-only on the backend (require_role("admin")) — the frontend
// hides this action for non-admins too (see admin-notifications.js) but
// the real enforcement is server-side, same as everywhere else in this app.
async function approveNotification(notificationId) {
  return adminFetch(`/admin/notifications/${encodeURIComponent(notificationId)}/approve`, {
    method: "POST",
  });
}

async function returnNotificationToDraft(notificationId) {
  return adminFetch(`/admin/notifications/${encodeURIComponent(notificationId)}/return-to-draft`, {
    method: "POST",
  });
}

async function sendNotification(notificationId) {
  return adminFetch(`/admin/notifications/${encodeURIComponent(notificationId)}/send`, {
    method: "POST",
  });
}

// --- Inbound Communication (Step 3) -----------------------------------------

// Inbound messages that don't (yet) have a resulting draft -- unknown
// sender, AI processing failure, or still pending. A message that did get
// drafted already shows up as that draft in the regular notifications list.
async function getCommunicationsInbox() {
  return adminFetch("/admin/communications/inbox");
}

// Fetch + process any currently-unread inbound email right now, rather
// than waiting for the backend's own periodic background poll.
async function checkForNewEmail() {
  return adminFetch("/admin/communications/check-email", { method: "POST" });
}
