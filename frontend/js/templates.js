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

function createTemplateMedia(template) {
  const img = document.createElement("img");
  img.alt = `${template.name} cake template`;
  img.width = 640;
  img.height = 480;
  img.loading = "lazy";
  img.onerror = () => {
    img.onerror = null;
    img.src = "assets/images/hero-cake.svg";
  };

  if (!template.preview_image) {
    img.src = "assets/images/hero-cake.svg";
    return img;
  }

  // preview_image points at the .webp; the same-named .jpg is the fallback
  // for browsers without WebP support (generated alongside it).
  const webpUrl = `assets/images/${template.preview_image}`;
  const jpgUrl = webpUrl.replace(/\.webp$/, ".jpg");

  const source = document.createElement("source");
  source.srcset = webpUrl;
  source.type = "image/webp";

  img.src = jpgUrl;

  const picture = document.createElement("picture");
  picture.append(source, img);
  return picture;
}

function createTemplateCard(template) {
  const article = document.createElement("article");
  article.className = "collection-card";

  const media = createTemplateMedia(template);

  const title = document.createElement("h3");
  title.textContent = template.name;

  const price = document.createElement("p");
  price.className = "template-price";
  price.textContent = `From $${Math.round(template.base_price)}`;

  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn btn-small";
  button.textContent = "Design This Cake";

  button.addEventListener("click", () => {
    navigateToDesigner(template.id);
  });

  article.append(media, title, price, button);

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
