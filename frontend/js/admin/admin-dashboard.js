// CakeCraft Studio Backoffice — Dashboard page.
// Every render function below builds DOM nodes via createElement +
// textContent rather than innerHTML + interpolation, because some of the
// values it displays (customer names on recent orders) ultimately come
// from the public, unauthenticated order form — never trust that into
// innerHTML in a page that also holds the admin's session token.

function renderStats(data) {
  document.getElementById("statTotalOrders").textContent = data.totalOrders;
  document.getElementById("statTodaysOrders").textContent = data.todaysOrders;

  const breakdown = document.getElementById("statusBreakdown");
  breakdown.innerHTML = "";
  Object.entries(data.ordersByStatus).forEach(([status, count]) => {
    const row = document.createElement("div");
    row.className = "admin-status-breakdown__row";

    row.appendChild(renderStatusBadge(status));

    const countEl = document.createElement("span");
    countEl.className = "admin-status-breakdown__count";
    countEl.textContent = String(count);
    row.appendChild(countEl);

    breakdown.appendChild(row);
  });
}

function renderRecentOrders(orders) {
  const container = document.getElementById("recentOrdersContainer");
  container.innerHTML = "";

  if (orders.length === 0) {
    renderEmptyState(container, "No orders yet.");
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
    tr.addEventListener("click", () => {
      window.location.href = `admin-orders.html?id=${encodeURIComponent(order.id)}`;
    });

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  container.appendChild(table);
}

function renderRecentAuditEvents(events) {
  const container = document.getElementById("recentAuditContainer");
  container.innerHTML = "";

  if (events.length === 0) {
    renderEmptyState(container, "No audit events yet.");
    return;
  }

  const list = document.createElement("ul");
  list.className = "admin-audit-list";

  events.forEach((event) => {
    const li = document.createElement("li");

    const actionEl = document.createElement("span");
    actionEl.className = "admin-audit-list__action";
    actionEl.textContent = event.action;

    const metaEl = document.createElement("span");
    metaEl.className = "admin-audit-list__meta";
    const actorName = event.staff_profiles ? event.staff_profiles.name : "System";
    metaEl.textContent = `${actorName} · ${formatDateTime(event.created_at)}`;

    li.append(actionEl, metaEl);
    list.appendChild(li);
  });

  container.appendChild(list);
}

function renderSystemHealth(health) {
  const container = document.getElementById("systemHealthContainer");
  container.innerHTML = "";

  const grid = document.createElement("div");
  grid.className = "admin-health-grid";

  const rows = [
    { label: "Backend", status: health.backend.status, detail: null },
    {
      label: "Database",
      status: health.database.status,
      detail: health.database.latencyMs != null ? `${health.database.latencyMs} ms` : null,
    },
    { label: "Railway", status: health.railway.status, detail: health.railway.environment },
    { label: "Netlify", status: health.netlify.status, detail: health.netlify.note },
    {
      label: "Last Deployment",
      status: health.lastDeployment.commitSha ? "known" : "unavailable",
      detail: health.lastDeployment.commitSha
        ? health.lastDeployment.commitSha.slice(0, 7)
        : "Not available",
    },
  ];

  rows.forEach(({ label, status, detail }) => {
    const item = document.createElement("div");
    item.className = "admin-health-item";

    const labelEl = document.createElement("span");
    labelEl.className = "admin-health-item__label";
    labelEl.textContent = label;

    const statusEl = document.createElement("span");
    statusEl.className = `admin-health-item__status admin-health-item__status--${status}`;
    statusEl.textContent = status;

    item.append(labelEl, statusEl);

    if (detail) {
      const detailEl = document.createElement("span");
      detailEl.className = "admin-health-item__detail";
      detailEl.textContent = detail;
      item.appendChild(detailEl);
    }

    grid.appendChild(item);
  });

  container.appendChild(grid);
}

// --- AI Daily Briefing (Final AI Intelligence Phase) ------------------------
// The dashboard's centerpiece: today's stats, tomorrow's ML forecast, and
// rule-based recommendations, composed server-side by briefing_service.py.
// Loaded independently of the stat cards/panels below (own try/catch, own
// refresh button) so a briefing failure never blocks the rest of the
// dashboard, and vice versa.

function buildBriefingStat(label, value) {
  const stat = document.createElement("div");
  stat.className = "admin-briefing__stat";

  const labelEl = document.createElement("p");
  labelEl.className = "admin-briefing__stat-label";
  labelEl.textContent = label;

  const valueEl = document.createElement("p");
  valueEl.className = "admin-briefing__stat-value";
  valueEl.textContent = value;

  stat.append(labelEl, valueEl);
  return stat;
}

function renderWorkloadBadge(level) {
  const span = document.createElement("span");
  const key = level.toLowerCase().replace(/\s+/g, "_");
  span.className = `status-badge status-badge--workload-${key}`;
  span.textContent = level;
  return span;
}

function renderForecastCard(forecast) {
  const card = document.createElement("div");
  card.className = "admin-briefing__forecast";

  const heading = document.createElement("h3");
  heading.textContent = `Tomorrow's Forecast — ${forecast.weekday}, ${forecast.date}`;
  card.appendChild(heading);

  const metrics = document.createElement("div");
  metrics.className = "admin-briefing__forecast-metrics";

  const addMetric = (label, valueNode) => {
    const wrap = document.createElement("div");
    wrap.className = "admin-briefing__forecast-metric";
    const labelEl = document.createElement("span");
    labelEl.className = "admin-briefing__forecast-metric-label";
    labelEl.textContent = label;
    wrap.append(labelEl, valueNode);
    metrics.appendChild(wrap);
  };

  const ordersValue = document.createElement("span");
  ordersValue.className = "admin-briefing__forecast-metric-value";
  ordersValue.textContent = String(forecast.predictedOrders);
  addMetric("Predicted Orders", ordersValue);

  const revenueValue = document.createElement("span");
  revenueValue.className = "admin-briefing__forecast-metric-value";
  revenueValue.textContent = formatCurrency(forecast.predictedRevenue);
  addMetric("Predicted Revenue", revenueValue);

  addMetric("Workload", renderWorkloadBadge(forecast.workloadLevel));

  const confidenceValue = document.createElement("span");
  confidenceValue.className = "admin-briefing__forecast-metric-value";
  confidenceValue.textContent = `${forecast.confidence}%`;
  addMetric("Confidence", confidenceValue);

  card.appendChild(metrics);

  // The Explainable AI requirement, literally: every forecast ships with
  // a plain-English reason built from the same numbers above.
  const reason = document.createElement("p");
  reason.className = "admin-briefing__reason";
  reason.textContent = forecast.reason;
  card.appendChild(reason);

  return card;
}

function renderHighPriorityOrders(orders) {
  const section = document.createElement("div");
  section.className = "admin-briefing__section";

  const heading = document.createElement("h3");
  heading.textContent = "High Priority Orders";
  section.appendChild(heading);

  if (orders.length === 0) {
    const empty = document.createElement("p");
    empty.className = "admin-state admin-state--empty";
    empty.textContent = "Nothing urgent right now.";
    section.appendChild(empty);
    return section;
  }

  const list = document.createElement("ul");
  list.className = "admin-briefing__priority-list";

  orders.forEach((order) => {
    const li = document.createElement("li");
    li.className = "admin-briefing__priority-item";
    li.addEventListener("click", () => {
      window.location.href = `admin-orders.html?id=${encodeURIComponent(order.id)}`;
    });

    const main = document.createElement("div");
    const title = document.createElement("span");
    title.className = "admin-briefing__priority-title";
    title.textContent = `${order.customerName || "—"} · ${order.templateName || "—"}`;
    const reason = document.createElement("span");
    reason.className = "admin-briefing__priority-reason";
    reason.textContent = order.reason;
    main.append(title, reason);

    li.append(main, renderStatusBadge(order.status));
    list.appendChild(li);
  });

  section.appendChild(list);
  return section;
}

function renderRecommendedActions(actions) {
  const section = document.createElement("div");
  section.className = "admin-briefing__section";

  const heading = document.createElement("h3");
  heading.textContent = "Recommended Actions";
  section.appendChild(heading);

  const list = document.createElement("ul");
  list.className = "admin-briefing__actions";
  actions.forEach((action) => {
    const li = document.createElement("li");
    li.textContent = action;
    list.appendChild(li);
  });
  section.appendChild(list);

  return section;
}

function renderBriefing(data) {
  const container = document.getElementById("briefingContainer");
  container.innerHTML = "";

  document.getElementById("briefingGeneratedAt").textContent = `Generated ${formatDateTime(data.generatedAt)}`;

  const grid = document.createElement("div");
  grid.className = "admin-briefing__grid";
  grid.appendChild(buildBriefingStat("Today's Orders", String(data.todaysOrders)));
  grid.appendChild(buildBriefingStat("Today's Revenue", formatCurrency(data.todaysRevenue)));
  grid.appendChild(buildBriefingStat("Pending Notifications", String(data.pendingNotifications.total)));
  container.appendChild(grid);

  container.appendChild(renderForecastCard(data.forecast));
  container.appendChild(renderHighPriorityOrders(data.highPriorityOrders));
  container.appendChild(renderRecommendedActions(data.recommendedActions));
}

async function loadBriefing() {
  const container = document.getElementById("briefingContainer");
  renderLoadingState(container, "Composing today's briefing…");
  try {
    const data = await getDailyBriefing();
    renderBriefing(data);
  } catch (error) {
    renderErrorState(container, "Unable to load the AI Daily Briefing. Please try again.");
  }
}

function initBriefingRefreshButton() {
  const button = document.getElementById("refreshBriefingBtn");
  if (!button) return;
  button.addEventListener("click", loadBriefing);
}

// --- AI Operations Agent + RAG (Business Intelligence Layer) ---------------
// Extends the AI Daily Briefing panel with the Agent's synthesized
// narrative, and adds a standalone "Ask the AI Agent" box combining live
// data + the ML forecast + RAG knowledge. Text is rendered via
// textContent throughout, matching this file's own established
// convention, even though this content is AI-generated rather than
// customer-submitted — one security posture, not two.

function renderAgentBriefing(data) {
  const container = document.getElementById("agentBriefingContainer");
  container.innerHTML = "";

  const wrap = document.createElement("div");
  wrap.className = "admin-agent-briefing";

  const heading = document.createElement("h3");
  heading.textContent = "AI Agent Insights";
  wrap.appendChild(heading);

  const narrative = document.createElement("p");
  narrative.className = "admin-agent-briefing__narrative";
  narrative.textContent = data.narrative;
  wrap.appendChild(narrative);

  const notes = [
    ["Production", data.productionNotes],
    ["Staffing", data.staffingNotes],
    ["Inventory", data.inventoryNotes],
  ].filter(([, value]) => value);

  if (notes.length > 0) {
    const grid = document.createElement("div");
    grid.className = "admin-agent-briefing__notes";
    notes.forEach(([label, value]) => {
      const item = document.createElement("div");
      item.className = "admin-agent-briefing__note";

      const labelEl = document.createElement("span");
      labelEl.className = "admin-agent-briefing__note-label";
      labelEl.textContent = label;

      const valueEl = document.createElement("p");
      valueEl.textContent = value;

      item.append(labelEl, valueEl);
      grid.appendChild(item);
    });
    wrap.appendChild(grid);
  }

  if (data.sources && data.sources.length > 0) {
    const sources = document.createElement("p");
    sources.className = "admin-agent-briefing__sources";
    sources.textContent = "Grounded in: " + data.sources.map((s) => s.title).join(", ");
    wrap.appendChild(sources);
  }

  container.appendChild(wrap);
}

async function loadAgentBriefing() {
  const container = document.getElementById("agentBriefingContainer");
  renderLoadingState(container, "Loading AI Agent Insights…");
  try {
    const data = await getAgentMorningBriefing();
    renderAgentBriefing(data);
  } catch (error) {
    // A non-critical add-on to the main briefing above it — fail
    // quietly rather than showing an error state stacked on a panel
    // that's already working.
    container.innerHTML = "";
  }
}

function renderAgentAskResult(data) {
  const container = document.getElementById("agentAskResult");
  container.innerHTML = "";

  const answer = document.createElement("p");
  answer.className = "admin-agent-ask-answer";
  answer.textContent = data.answer;
  container.appendChild(answer);

  if (data.sources && data.sources.length > 0) {
    const sources = document.createElement("p");
    sources.className = "admin-agent-briefing__sources";
    sources.textContent = "Sources: " + data.sources.map((s) => s.title).join(", ");
    container.appendChild(sources);
  }
}

function initAgentAskForm() {
  const form = document.getElementById("agentAskForm");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("agentAskInput");
    const question = input.value.trim();
    if (!question) return;

    const resultContainer = document.getElementById("agentAskResult");
    const submitButton = form.querySelector("button[type=submit]");
    renderLoadingState(resultContainer, "Thinking…");
    submitButton.disabled = true;

    try {
      const data = await askAgent(question);
      renderAgentAskResult(data);
    } catch (error) {
      renderErrorState(resultContainer, "Unable to get an answer. Please try again.");
    } finally {
      submitButton.disabled = false;
    }
  });
}

// --- AI Knowledge Assistant (RAG) -------------------------------------------
// A dedicated frontend entry point for the existing, already-working
// POST /admin/rag/ask endpoint (rag_service.py, unmodified). Mirrors the
// "Ask the AI Operations Agent" box above exactly — same form pattern,
// same loading/error helpers, same result/sources rendering shape — just
// pointed at the RAG-only endpoint instead of the Agent's.

function renderRagAskResult(data) {
  const container = document.getElementById("ragAskResult");
  container.innerHTML = "";

  const answer = document.createElement("p");
  answer.className = "admin-agent-ask-answer";
  answer.textContent = data.answer;
  container.appendChild(answer);

  if (data.sources && data.sources.length > 0) {
    const sources = document.createElement("p");
    sources.className = "admin-agent-briefing__sources";
    sources.textContent = "Sources: " + data.sources.map((s) => s.title).join(", ");
    container.appendChild(sources);
  }
}

function initRagAskForm() {
  const form = document.getElementById("ragAskForm");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("ragAskInput");
    const question = input.value.trim();
    if (!question) return;

    const resultContainer = document.getElementById("ragAskResult");
    const submitButton = form.querySelector("button[type=submit]");
    renderLoadingState(resultContainer, "Searching the knowledge base…");
    submitButton.disabled = true;

    try {
      const data = await askRag(question);
      renderRagAskResult(data);
    } catch (error) {
      renderErrorState(resultContainer, "Unable to get an answer. Please try again.");
    } finally {
      submitButton.disabled = false;
    }
  });
}

async function loadDashboard() {
  const panelsGrid = document.querySelector(".admin-panels-grid");

  renderLoadingState(document.getElementById("recentOrdersContainer"), "Loading recent orders…");
  renderLoadingState(document.getElementById("recentAuditContainer"), "Loading recent audit events…");
  renderLoadingState(document.getElementById("systemHealthContainer"), "Loading system health…");

  try {
    const data = await getDashboard();
    renderStats(data);
    renderRecentOrders(data.recentOrders);
    renderRecentAuditEvents(data.recentAuditEvents);
    renderSystemHealth(data.systemHealth);
  } catch (error) {
    if (panelsGrid) renderErrorState(panelsGrid, "Unable to load the dashboard. Please try again.");
  }
}

function initRefreshButton() {
  const button = document.getElementById("refreshDashboardBtn");
  if (!button) return;
  button.addEventListener("click", loadDashboard);
}

document.addEventListener("DOMContentLoaded", () => {
  loadDashboard();
  loadBriefing();
  loadAgentBriefing();
  initRefreshButton();
  initBriefingRefreshButton();
  initAgentAskForm();
  initRagAskForm();
});
