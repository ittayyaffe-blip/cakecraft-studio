// CakeCraft Studio — API communication only. No rendering logic here.

// Same hostname the page was loaded from, so this works unchanged on
// localhost/127.0.0.1 for desktop dev, and automatically targets the
// right LAN IP (e.g. http://192.168.1.140:8000) when the frontend is
// opened from another device, as long as the backend is reachable there.
const API_BASE_URL = "https://web-production-c9dd99.up.railway.app";

// Every request gets a client-side ceiling so a slow/stuck backend call
// never leaves the customer staring at a frozen page -- pairs with the
// backend's own bounded timeouts (agent_service._claude, the Supabase
// client in app/core/database.py) added for the same reason. Chat/order/
// payment calls get a longer budget since they may involve a real Claude
// call or several sequential steps; simple reads should always be fast.
const DEFAULT_TIMEOUT_MS = 15000;
const CHAT_TIMEOUT_MS = 45000;

async function fetchWithTimeout(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Request timed out");
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function getCollections() {
  const response = await fetchWithTimeout(`${API_BASE_URL}/collections`);

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}

async function getTemplates(collection) {
  const url = collection
    ? `${API_BASE_URL}/templates?collection=${encodeURIComponent(collection)}`
    : `${API_BASE_URL}/templates`;

  const response = await fetchWithTimeout(url);

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}

async function getDesignerInit(templateId) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/designer/${encodeURIComponent(templateId)}`);

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}

async function createOrder(order) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(order),
  });

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}

// Minimal, unauthenticated, no-PII order view -- backs the payment page
// (see app/schemas/order.py's OrderPublicView for exactly what this
// returns and why).
async function getOrder(orderId) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/orders/${encodeURIComponent(orderId)}`);

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}

// Simulated/demo payment -- no amount is ever sent from here; the backend
// always charges (simulated) orders.total_price, see payment_service.py.
// Idempotent server-side (see simulate_payment's own docstring), so a
// timeout/failure here is always safe to retry -- a retry either
// completes the same payment or, if it already succeeded, returns that
// same result unchanged rather than charging (simulated) twice.
async function payOrder(orderId) {
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/orders/${encodeURIComponent(orderId)}/pay`,
    { method: "POST" },
    CHAT_TIMEOUT_MS
  );

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}

async function askChat(payload) {
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/chat/ask`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
    CHAT_TIMEOUT_MS
  );

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}

// Chat-assisted ordering MVP -- one turn of slot collection/confirmation.
// `draft` is whatever the previous turn's response.draft was (or absent
// on the very first turn); the caller (chat-widget.js) just round-trips
// it, never inspects/builds it itself.
async function askChatOrder(payload) {
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/chat/order`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
    CHAT_TIMEOUT_MS
  );

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}
