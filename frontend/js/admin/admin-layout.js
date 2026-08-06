// CakeCraft Studio Backoffice — shared shell behavior for every admin page
// (sidebar toggle, active-nav highlighting, current-admin display, logout).
// Mirrors app.js's role on the customer side: cross-page concerns only,
// included on every page that uses the admin shell (not admin-login.html,
// which has no sidebar/topbar).

function initAdminSidebarToggle() {
  const toggle = document.getElementById("adminSidebarToggle");
  const sidebar = document.getElementById("adminSidebar");
  if (!toggle || !sidebar) return;

  toggle.addEventListener("click", () => {
    const isOpen = sidebar.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", String(isOpen));
  });
}

function highlightActiveNavLink() {
  const currentPage = window.location.pathname.split("/").pop();
  document.querySelectorAll(".admin-nav-link").forEach((link) => {
    if (link.getAttribute("href") === currentPage) {
      link.classList.add("is-active");
      link.setAttribute("aria-current", "page");
    }
  });
}

async function initAdminAccount() {
  const whoEl = document.getElementById("adminWho");
  if (!whoEl) return;

  try {
    const me = await getAdminMe();
    whoEl.textContent = `${me.email} · ${me.role}`;
  } catch {
    // adminFetch already redirects to admin-login.html on 401 — nothing
    // else to do for any other failure here.
  }
}

function initAdminLogout() {
  const button = document.getElementById("adminLogoutBtn");
  if (!button) return;

  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await adminLogout();
    } catch {
      // Best-effort: still clear the local session and leave below.
    }
    clearAdminSession();
    window.location.href = "admin-login.html";
  });
}

function initAdminShell() {
  requireAdminAuth();
  initAdminSidebarToggle();
  highlightActiveNavLink();
  initAdminAccount();
  initAdminLogout();
}

document.addEventListener("DOMContentLoaded", initAdminShell);
