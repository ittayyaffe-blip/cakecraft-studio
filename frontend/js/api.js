// CakeCraft Studio — API communication only. No rendering logic here.

const API_BASE_URL = "http://127.0.0.1:8000";

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
