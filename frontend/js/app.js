// CakeCraft Studio — landing page interactions
// No backend calls here yet: mobile nav toggle + footer year only.

function initNavToggle() {
  const toggle = document.getElementById("navToggle");
  const nav = document.getElementById("siteNav");
  if (!toggle || !nav) return;

  toggle.addEventListener("click", () => {
    const isOpen = nav.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", String(isOpen));
  });

  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      nav.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
    });
  });
}

function initFooterYear() {
  const yearEl = document.getElementById("year");
  if (yearEl) {
    yearEl.textContent = String(new Date().getFullYear());
  }
}

async function loadCollections() {
  const container = document.getElementById("collectionsGrid");
  if (!container) return;

  renderCollectionsLoading(container);

  try {
    const collections = await getCollections();

    if (collections.length === 0) {
      renderCollectionsEmpty(container);
      return;
    }

    renderCollections(container, collections);
  } catch (error) {
    renderCollectionsError(container);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initNavToggle();
  initFooterYear();
  loadCollections();
});
