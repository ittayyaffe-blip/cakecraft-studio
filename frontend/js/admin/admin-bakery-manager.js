// CakeCraft Studio Backoffice — AI Bakery Manager (admin-dashboard.html).
// Optional, additive orchestration layer: Preview Plan (read-only) opens
// a drawer with a proposed plan; Execute Approved Plan runs only the
// manager's checkbox-selected, backend-revalidated actions. The manual
// Back Office (Orders, Communications, this same Dashboard's other
// sections) is completely untouched by this file and keeps working
// exactly as before if any part of this fails — see initBakeryManager's
// own try/catch.
//
// Same "no innerHTML + interpolation for server-derived text" convention
// every other admin-*.js file already follows (order reasons/evidence
// strings ultimately come from Claude's own output, via the backend) --
// everything below is built with createElement/textContent.

const BAKERY_MANAGER_ACTION_LABELS = {
  advance_to_in_progress: "Move to In Progress",
  advance_to_ready: "Move to Ready",
  advance_to_completed: "Move to Completed",
  create_customer_update_draft: "Create customer-update draft",
  create_staff_note_draft: "Create staff-note draft",
  reprioritize_production: "Reprioritize production",
  staffing_adjustment: "Staffing adjustment",
  inventory_check: "Inventory check",
  rush_order_attention: "Rush-order attention",
};

function bakeryPlanActionLabel(actionType) {
  return BAKERY_MANAGER_ACTION_LABELS[actionType] || actionType;
}

// --- Drawer open/close -------------------------------------------------

function openBakeryManagerDrawer() {
  document.getElementById("bakeryManagerDrawerBackdrop").classList.remove("is-hidden");
  const drawer = document.getElementById("bakeryManagerDrawer");
  drawer.classList.remove("is-hidden");
  drawer.setAttribute("aria-hidden", "false");
}

function closeBakeryManagerDrawer() {
  document.getElementById("bakeryManagerDrawerBackdrop").classList.add("is-hidden");
  const drawer = document.getElementById("bakeryManagerDrawer");
  drawer.classList.add("is-hidden");
  drawer.setAttribute("aria-hidden", "true");
}

// --- Rendering -----------------------------------------------------------

function appendBakeryPlanHeading(container, text) {
  const heading = document.createElement("h3");
  heading.className = "admin-drawer__section-heading";
  heading.textContent = text;
  container.appendChild(heading);
}

function appendBakeryPlanAction(container, action) {
  const row = document.createElement("div");
  row.className = "bakery-plan-action";

  if (action.safeToExecute) {
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "bakery-plan-action__checkbox";
    checkbox.dataset.actionId = action.actionId;
    checkbox.addEventListener("change", refreshBakeryExecuteButtonState);
    row.appendChild(checkbox);
  } else {
    const spacer = document.createElement("span");
    spacer.setAttribute("aria-hidden", "true");
    spacer.style.width = "1.1rem";
    spacer.style.flexShrink = "0";
    row.appendChild(spacer);
  }

  const body = document.createElement("div");
  body.className = "bakery-plan-action__body";

  const title = document.createElement("p");
  title.className = "bakery-plan-action__title";
  title.textContent = bakeryPlanActionLabel(action.actionType);
  if (!action.safeToExecute) {
    const badge = document.createElement("span");
    badge.className = "bakery-plan-action__badge status-badge--handling-yellow";
    badge.textContent = "Recommendation Only";
    title.appendChild(document.createTextNode(" "));
    title.appendChild(badge);
  }
  body.appendChild(title);

  const reason = document.createElement("p");
  reason.className = "bakery-plan-action__reason";
  reason.textContent = action.reason;
  body.appendChild(reason);

  if (action.evidence && action.evidence.length > 0) {
    const list = document.createElement("ul");
    list.className = "bakery-plan-action__evidence";
    action.evidence.forEach((line) => {
      const li = document.createElement("li");
      li.textContent = line;
      list.appendChild(li);
    });
    body.appendChild(list);
  }

  row.appendChild(body);
  container.appendChild(row);
}

function appendBakeryPlanExceptions(container, exceptions) {
  if (!exceptions || exceptions.length === 0) return;
  exceptions.forEach((exception) => {
    const callout = document.createElement("div");
    callout.className = "admin-review-callout";
    const title = document.createElement("p");
    title.className = "admin-review-callout__title";
    title.textContent = exception.type.replace(/_/g, " ");
    const detail = document.createElement("p");
    detail.textContent = exception.detail;
    callout.append(title, detail);
    container.appendChild(callout);
  });
}

function appendBakeryPlanList(container, label, items) {
  if (!items || items.length === 0) return;
  const heading = document.createElement("p");
  heading.className = "bakery-plan-action__title";
  heading.textContent = label;
  container.appendChild(heading);
  const list = document.createElement("ul");
  list.className = "bakery-plan-action__evidence";
  items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  });
  container.appendChild(list);
}

let _currentBakeryPlan = null;

function renderBakeryManagerPlan(plan) {
  _currentBakeryPlan = plan;
  const body = document.getElementById("bakeryManagerDrawerBody");
  body.innerHTML = "";

  const meta = document.createElement("p");
  meta.className = "admin-briefing__generated";
  meta.textContent = `Run ${plan.runId} — ${formatDateTime(plan.timestamp)}`;
  body.appendChild(meta);

  appendBakeryPlanHeading(body, "Operational Summary");
  const summary = document.createElement("p");
  summary.textContent = plan.operationalSummary;
  body.appendChild(summary);

  appendBakeryPlanHeading(body, "Proposed Actions");
  const executable = plan.proposedActions.filter((a) => a.safeToExecute);
  if (plan.proposedActions.length === 0) {
    const empty = document.createElement("p");
    empty.className = "admin-state admin-state--empty";
    empty.textContent = "No production actions are safe to automate right now.";
    body.appendChild(empty);
  } else {
    if (executable.length === 0) {
      const note = document.createElement("p");
      note.className = "admin-state admin-state--empty";
      note.textContent = "No production actions are safe to automate right now — see the recommendations below.";
      body.appendChild(note);
    }
    plan.proposedActions.forEach((action) => appendBakeryPlanAction(body, action));
  }

  appendBakeryPlanHeading(body, "Recommendations");
  const rec = plan.recommendations || {};
  const hasRecommendations =
    (rec.production || []).length + (rec.staffing || []).length + (rec.inventory || []).length + (rec.workload || []).length > 0;
  if (!hasRecommendations) {
    const none = document.createElement("p");
    none.className = "admin-state admin-state--empty";
    none.textContent = "No additional recommendations right now.";
    body.appendChild(none);
  } else {
    appendBakeryPlanList(body, "Production", rec.production);
    appendBakeryPlanList(body, "Staffing", rec.staffing);
    appendBakeryPlanList(body, "Inventory", rec.inventory);
    appendBakeryPlanList(body, "Workload", rec.workload);
  }

  appendBakeryPlanHeading(body, "Exceptions / Manager Attention");
  if (!plan.exceptions || plan.exceptions.length === 0) {
    const none = document.createElement("p");
    none.className = "admin-state admin-state--empty";
    none.textContent = "No exceptions.";
    body.appendChild(none);
  } else {
    appendBakeryPlanExceptions(body, plan.exceptions);
  }

  // Execute section
  appendBakeryPlanHeading(body, "Execute");
  const executeBtn = document.createElement("button");
  executeBtn.type = "button";
  executeBtn.className = "btn btn-primary";
  executeBtn.id = "bakeryManagerExecuteBtn";
  executeBtn.textContent = "Execute Approved Plan";
  executeBtn.disabled = true;
  executeBtn.addEventListener("click", handleBakeryManagerExecute);
  body.appendChild(executeBtn);

  const resultContainer = document.createElement("div");
  resultContainer.id = "bakeryManagerExecuteResult";
  body.appendChild(resultContainer);
}

function refreshBakeryExecuteButtonState() {
  const btn = document.getElementById("bakeryManagerExecuteBtn");
  if (!btn) return;
  const anyChecked = document.querySelectorAll(".bakery-plan-action__checkbox:checked").length > 0;
  btn.disabled = !anyChecked || btn.dataset.executing === "true";
}

// --- Preview -------------------------------------------------------------

async function handleBakeryManagerPreview() {
  const btn = document.getElementById("bakeryManagerPreviewBtn");
  const status = document.getElementById("bakeryManagerStatus");
  if (btn.disabled) return; // guard against a duplicate click while a request is already in flight

  btn.disabled = true;
  status.className = "admin-state";
  status.setAttribute("role", "status");
  status.textContent = "Analyzing bakery operations…";

  try {
    const plan = await previewBakeryManagerPlan();
    status.className = "admin-state is-hidden";
    renderBakeryManagerPlan(plan);
    openBakeryManagerDrawer();
  } catch (error) {
    status.className = "admin-state admin-state--error";
    status.setAttribute("role", "alert");
    status.textContent =
      "AI Bakery Manager couldn't generate a plan right now. The manual Back Office remains fully available.";
  } finally {
    btn.disabled = false;
  }
}

// --- Execute ---------------------------------------------------------------

async function handleBakeryManagerExecute() {
  const btn = document.getElementById("bakeryManagerExecuteBtn");
  if (btn.disabled || btn.dataset.executing === "true") return; // guard against a duplicate click

  const selectedIds = Array.from(document.querySelectorAll(".bakery-plan-action__checkbox:checked")).map(
    (cb) => cb.dataset.actionId
  );
  const selectedActions = _currentBakeryPlan.proposedActions
    .filter((a) => selectedIds.includes(a.actionId))
    .map((a) => ({
      actionId: a.actionId,
      actionType: a.actionType,
      orderId: a.orderId,
      customerId: a.customerId,
      proposedState: a.proposedState,
    }));

  btn.dataset.executing = "true";
  btn.disabled = true;
  btn.textContent = "Executing approved actions…";

  const resultContainer = document.getElementById("bakeryManagerExecuteResult");
  resultContainer.innerHTML = "";

  try {
    const response = await executeBakeryManagerPlan(_currentBakeryPlan.runId, selectedActions);
    renderBakeryManagerExecuteResults(resultContainer, response.results);
  } catch (error) {
    const errorMsg = document.createElement("p");
    errorMsg.className = "admin-state admin-state--error";
    errorMsg.setAttribute("role", "alert");
    errorMsg.textContent = error.message || "Failed to execute the approved plan.";
    resultContainer.appendChild(errorMsg);
  } finally {
    btn.textContent = "Execute Approved Plan";
    btn.dataset.executing = "false";
    btn.disabled = true; // stays disabled -- re-running the same selection isn't meaningful without a fresh Preview
  }
}

function renderBakeryManagerExecuteResults(container, results) {
  const heading = document.createElement("h3");
  heading.className = "admin-drawer__section-heading";
  heading.textContent = "AI Bakery Manager Run Complete";
  container.appendChild(heading);

  const succeeded = results.filter((r) => r.success);
  const failed = results.filter((r) => !r.success);

  const summary = document.createElement("p");
  summary.textContent = `${succeeded.length} action${succeeded.length === 1 ? "" : "s"} executed. ${
    failed.length > 0 ? `${failed.length} action${failed.length === 1 ? "" : "s"} could not be executed.` : ""
  }`;
  container.appendChild(summary);

  results.forEach((result) => {
    const row = document.createElement("div");
    row.className = "bakery-plan-action";

    const body = document.createElement("div");
    body.className = "bakery-plan-action__body";

    const title = document.createElement("p");
    title.className = "bakery-plan-action__title";
    title.textContent = `${bakeryPlanActionLabel(result.actionType)} — ${result.success ? "Success" : "Failed"}`;
    body.appendChild(title);

    const detail = document.createElement("p");
    detail.className = "bakery-plan-action__reason";
    detail.textContent = result.detail;
    body.appendChild(detail);

    if (result.success && result.orderId) {
      const link = document.createElement("a");
      link.className = "btn btn-small";
      link.href = `admin-orders.html?id=${encodeURIComponent(result.orderId)}`;
      link.textContent = "View Order";
      body.appendChild(link);
    }
    if (result.success && result.notificationId) {
      const link = document.createElement("a");
      link.className = "btn btn-small";
      link.href = `admin-notifications.html?id=${encodeURIComponent(result.notificationId)}`;
      link.textContent = "Review Communication";
      body.appendChild(link);
    }

    row.appendChild(body);
    container.appendChild(row);
  });

  const auditNote = document.createElement("p");
  auditNote.className = "admin-briefing__generated";
  auditNote.textContent = "Audit trail recorded for every action above.";
  container.appendChild(auditNote);
}

// --- Init ------------------------------------------------------------------

function initBakeryManager() {
  const previewBtn = document.getElementById("bakeryManagerPreviewBtn");
  if (!previewBtn) return; // this file is only loaded on admin-dashboard.html

  previewBtn.addEventListener("click", handleBakeryManagerPreview);
  document.getElementById("bakeryManagerDrawerClose").addEventListener("click", closeBakeryManagerDrawer);
  document.getElementById("bakeryManagerDrawerBackdrop").addEventListener("click", closeBakeryManagerDrawer);
}

document.addEventListener("DOMContentLoaded", () => {
  try {
    initBakeryManager();
  } catch (error) {
    // The manual Back Office (everything admin-dashboard.js renders) must
    // never be affected by this optional feature failing to initialize.
    console.error("AI Bakery Manager failed to initialize:", error);
  }
});
