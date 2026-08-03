// CakeCraft Studio — API communication only. No rendering logic here.

// Same hostname the page was loaded from, so this works unchanged on
// localhost/127.0.0.1 for desktop dev, and automatically targets the
// right LAN IP (e.g. http://192.168.1.140:8000) when the frontend is
// opened from another device, as long as the backend is reachable there.
const API_BASE_URL = `http://${window.location.hostname}:8000`;

async function getCollections() {
  const response = await fetch(`${API_BASE_URL}/collections`);

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}

async function getTemplates(collection) {
  const url = collection
    ? `${API_BASE_URL}/templates?collection=${encodeURIComponent(collection)}`
    : `${API_BASE_URL}/templates`;

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}

async function getDesignerInit(templateId) {
  const response = await fetch(`${API_BASE_URL}/designer/${encodeURIComponent(templateId)}`);

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}

async function createOrder(order) {
  const response = await fetch(`${API_BASE_URL}/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(order),
  });

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}
