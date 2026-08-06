// CakeCraft Studio Backoffice — admin login page.

function renderLoginError(message) {
  const errorEl = document.getElementById("adminLoginError");
  if (errorEl) errorEl.textContent = message;
}

function redirectIfAlreadyLoggedIn() {
  if (isLoggedIn()) {
    window.location.href = "admin-dashboard.html";
  }
}

function initLoginForm() {
  const form = document.getElementById("adminLoginForm");
  const submitBtn = document.getElementById("adminLoginSubmit");
  if (!form || !submitBtn) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    renderLoginError("");
    submitBtn.disabled = true;

    const email = document.getElementById("adminEmail").value;
    const password = document.getElementById("adminPassword").value;

    try {
      const session = await adminLogin(email, password);
      saveAdminSession(session);
      window.location.href = "admin-dashboard.html";
    } catch (error) {
      renderLoginError(error.message || "Invalid email or password.");
      submitBtn.disabled = false;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  redirectIfAlreadyLoggedIn();
  initLoginForm();
});
