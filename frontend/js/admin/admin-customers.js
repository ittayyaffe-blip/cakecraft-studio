// CakeCraft Studio Backoffice — Customers page (list): search, paginate,
// click through to a profile. Search/page state lives in the URL query
// string, same convention as admin-orders.js and the customer-facing pages.
//
// Render functions build DOM via createElement + textContent, not
// innerHTML + interpolation — customer name/email/phone come from the
// public, unauthenticated order form (see admin-orders.js for the same
// rule and why it matters on a page holding the admin's session token).

const CUSTOMERS_PAGE_SIZE = 20;

function getCustomersStateFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return {
    search: params.get("search") || "",
    page: Number(params.get("page")) || 1,
  };
}

function setCustomersStateInUrl(state) {
  const params = new URLSearchParams();
  if (state.search) params.set("search", state.search);
  if (state.page && state.page !== 1) params.set("page", String(state.page));

  const query = params.toString();
  window.history.pushState({}, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
}

function renderCustomersTable(customers) {
  const container = document.getElementById("customersTableContainer");
  container.innerHTML = "";

  if (customers.length === 0) {
    renderEmptyState(container, "No customers match your search.");
    return;
  }

  const table = document.createElement("table");
  table.className = "admin-table";

  const thead = document.createElement("thead");
  thead.innerHTML =
    "<tr><th>Name</th><th>Email</th><th>Phone</th><th>Orders</th><th>Lifetime Value</th><th>Last Order</th></tr>";
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  customers.forEach((customer) => {
    const tr = document.createElement("tr");
    tr.className = "admin-table__row--clickable";
    tr.tabIndex = 0;

    const nameCell = document.createElement("td");
    nameCell.textContent = customer.name;

    const emailCell = document.createElement("td");
    emailCell.textContent = customer.email;

    const phoneCell = document.createElement("td");
    phoneCell.textContent = customer.phone || "—";

    const ordersCell = document.createElement("td");
    ordersCell.textContent = String(customer.orderCount);

    const valueCell = document.createElement("td");
    valueCell.textContent = formatCurrency(customer.lifetimeValue);

    const lastOrderCell = document.createElement("td");
    lastOrderCell.textContent = formatDateTime(customer.lastOrderDate);

    tr.append(nameCell, emailCell, phoneCell, ordersCell, valueCell, lastOrderCell);

    const open = () => {
      window.location.href = `admin-customer-detail.html?id=${encodeURIComponent(customer.id)}`;
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

function renderPagination(total, page, pageSize) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  document.getElementById("customersPageInfo").textContent =
    `Page ${page} of ${totalPages} (${total} customer${total === 1 ? "" : "s"})`;

  document.getElementById("customersPrevPage").disabled = page <= 1;
  document.getElementById("customersNextPage").disabled = page >= totalPages;
}

async function loadCustomers() {
  const state = getCustomersStateFromUrl();
  const container = document.getElementById("customersTableContainer");
  renderLoadingState(container, "Loading customers…");

  document.getElementById("customersSearchInput").value = state.search;

  try {
    const result = await getAdminCustomers({
      search: state.search || undefined,
      page: state.page,
      pageSize: CUSTOMERS_PAGE_SIZE,
    });
    renderCustomersTable(result.items);
    renderPagination(result.total, result.page, result.pageSize);
  } catch (error) {
    renderErrorState(container, "Unable to load customers. Please try again.");
  }
}

function initFilterForm() {
  const form = document.getElementById("customersFilterForm");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const search = document.getElementById("customersSearchInput").value.trim();
    setCustomersStateInUrl({ search, page: 1 });
    loadCustomers();
  });
}

function initPaginationButtons() {
  document.getElementById("customersPrevPage").addEventListener("click", () => {
    const state = getCustomersStateFromUrl();
    if (state.page > 1) {
      setCustomersStateInUrl({ ...state, page: state.page - 1 });
      loadCustomers();
    }
  });

  document.getElementById("customersNextPage").addEventListener("click", () => {
    const state = getCustomersStateFromUrl();
    setCustomersStateInUrl({ ...state, page: state.page + 1 });
    loadCustomers();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  loadCustomers();
  initFilterForm();
  initPaginationButtons();
});
