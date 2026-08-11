// CakeCraft Studio Backoffice — admin session storage only.
// The only file that reads/writes the admin auth token, mirroring how
// api.js is the only file allowed to call fetch() on the customer side.
// Session lives in sessionStorage (cleared when the tab closes) rather
// than localStorage — an admin session shouldn't silently outlive the
// browser tab it was opened in.

const ADMIN_SESSION_KEY = "cakecraft_admin_session";

function saveAdminSession(session) {
  sessionStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(session));
}

function getAdminSession() {
  const raw = sessionStorage.getItem(ADMIN_SESSION_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw);
  } catch {
    // Corrupted/non-JSON value -- treat exactly like "no session" rather
    // than letting the throw escape into getAuthHeader()/adminFetch(),
    // where it previously aborted before fetch() ever ran (zero network
    // requests, masked by loadNotifications()'s generic catch-all error).
    sessionStorage.removeItem(ADMIN_SESSION_KEY);
    return null;
  }
}

function clearAdminSession() {
  sessionStorage.removeItem(ADMIN_SESSION_KEY);
}

function isLoggedIn() {
  return getAdminSession() !== null;
}

function getAuthHeader() {
  const session = getAdminSession();
  return session ? { Authorization: `Bearer ${session.access_token}` } : {};
}

// Called at the top of every protected admin page, before anything else
// runs. Only checks that *some* session is stored — admin-api.js's 401
// handling covers a stored token that turns out to be invalid or expired.
function requireAdminAuth() {
  if (!isLoggedIn()) {
    window.location.href = "admin-login.html";
  }
}
