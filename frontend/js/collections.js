// CakeCraft Studio — renders the collections grid. No fetch calls here.

function renderCollectionsLoading(container) {
  container.innerHTML = '<p class="section-subtitle">Loading cake collections...</p>';
}

function renderCollectionsError(container) {
  container.innerHTML =
    '<p class="section-subtitle">Unable to load cake collections.<br>Please try again later.</p>';
}

function renderCollectionsEmpty(container) {
  container.innerHTML = '<p class="section-subtitle">No collections available.</p>';
}

function createCollectionCard(collection) {
  const article = document.createElement("article");
  article.className = "collection-card";

  const img = document.createElement("img");
  img.src = `assets/images/${collection.image}`;
  img.alt = `${collection.name} cake collection`;
  img.width = 640;
  img.height = 480;
  img.loading = "lazy";

  const title = document.createElement("h3");
  title.textContent = collection.name;

  const description = document.createElement("p");
  description.textContent = collection.description ?? "";

  article.append(img, title, description);
  return article;
}

function renderCollections(container, collections) {
  container.innerHTML = "";
  collections.forEach((collection) => {
    container.appendChild(createCollectionCard(collection));
  });
}
