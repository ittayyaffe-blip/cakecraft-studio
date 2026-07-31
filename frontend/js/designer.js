// CakeCraft Studio — Cake Designer foundation page.
// Reads the template id from the URL, calls the API, and renders template details.
// No fetch calls here (getTemplateById lives in api.js). No editing, no AI, yet.

function getTemplateIdFromUrl() {
  return new URLSearchParams(window.location.search).get("id");
}

function renderTemplateLoading() {
  const nameEl = document.getElementById("templateName");
  if (nameEl) nameEl.textContent = "Loading cake template...";
}

function renderTemplateError() {
  const nameEl = document.getElementById("templateName");
  if (nameEl) nameEl.textContent = "Unable to load this cake template. Please try again later.";
}

function renderTemplateDetail(template) {
  const img = document.getElementById("templateImage");
  const nameEl = document.getElementById("templateName");
  const collectionEl = document.getElementById("templateCollection");
  const styleEl = document.getElementById("templateStyle");
  const priceEl = document.getElementById("templateBasePrice");

  if (img) {
    img.src = template.preview_image
      ? `assets/images/${template.preview_image}`
      : "assets/images/hero-cake.svg";
    img.alt = `${template.name} cake template`;
  }
  if (nameEl) nameEl.textContent = template.name;
  if (collectionEl) collectionEl.textContent = template.category;
  if (styleEl) styleEl.textContent = template.style;
  if (priceEl) priceEl.textContent = `$${template.base_price.toFixed(2)}`;
}

async function loadTemplateDetail() {
  const id = getTemplateIdFromUrl();
  if (!id) {
    renderTemplateError();
    return;
  }

  renderTemplateLoading();

  try {
    const template = await getTemplateById(id);
    renderTemplateDetail(template);
  } catch (error) {
    renderTemplateError();
  }
}

function initStartDesigningButton() {
  const button = document.getElementById("startDesigningBtn");
  if (!button) return;
  button.addEventListener("click", () => {
    alert("Designer coming soon.");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  loadTemplateDetail();
  initStartDesigningButton();
});
