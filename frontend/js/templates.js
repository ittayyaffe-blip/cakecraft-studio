// CakeCraft Studio — Template Gallery page.
// Reads the collection from the URL, calls the API, and renders template cards.
// No fetch calls here (getTemplates lives in api.js).

function getCollectionFromUrl() {
  return new URLSearchParams(window.location.search).get("collection");
}

function renderTemplatesLoading(container) {
  container.innerHTML =
    '<p class="section-subtitle">Loading cake templates...</p>';
}

function renderTemplatesError(container) {
  container.innerHTML =
    '<p class="section-subtitle">Unable to load cake templates.<br>Please try again later.</p>';
}

function renderTemplatesEmpty(container) {
  container.innerHTML =
    '<p class="section-subtitle">No templates available for this collection.</p>';
}

function navigateToDesigner(templateId) {
  window.location.href = `designer.html?id=${encodeURIComponent(templateId)}`;
}

function createTemplateCard(template) {
  const article = document.createElement("article");
  article.className = "collection-card";

  const img = document.createElement("img");
  img.src = template.preview_image
    ? `assets/images/${template.preview_image}`
    : "assets/images/hero-cake.svg";

  img.alt = `${template.name} cake template`;
  img.width = 640;
  img.height = 480;
  img.loading = "lazy";

  const title = document.createElement("h3");
  title.textContent = template.name;

  const price = document.createElement("p");
  price.textContent = `Starting at $${template.base_price.toFixed(2)}`;

  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn btn-small";
  button.textContent = "Design This Cake";

  button.addEventListener("click", () => {
    navigateToDesigner(template.id);
  });

  article.append(img, title, price, button);

  return article;
}

function renderTemplates(container, templates) {
  container.innerHTML = "";

  templates.forEach((template) => {
    container.appendChild(createTemplateCard(template));
  });
}

async function loadTemplates() {
  const container = document.getElementById("templatesGrid");
  if (!container) return;

  const collection = getCollectionFromUrl();

  const titleEl = document.getElementById("collectionTitle");
  const subtitleEl = document.getElementById("collectionSubtitle");

  if (titleEl) {
    titleEl.textContent = collection
      ? `${collection} Cakes`
      : "All Cakes";
  }

  if (subtitleEl) {
    subtitleEl.textContent = collection
      ? `Browse our ${collection} collection.`
      : "Browse our full range of cake templates.";
  }

  renderTemplatesLoading(container);

  try {
    const templates = await getTemplates(collection);

    if (!templates || templates.length === 0) {
      renderTemplatesEmpty(container);
      return;
    }

    renderTemplates(container, templates);
  } catch (error) {
    console.error("Failed to load templates:", error);
    renderTemplatesError(container);
  }
}

document.addEventListener("DOMContentLoaded", loadTemplates);
