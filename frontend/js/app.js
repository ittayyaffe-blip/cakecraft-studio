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

// WhatsApp entry points -- landing page's "Questions Before You Order?"
// card and the footer link every other customer page has. Both read the
// destination from chat-widget.js's buildWhatsAppLink() (the one shared
// WHATSAPP_NUMBER constant) rather than a second hardcoded URL, so there
// is still only one place to update when the real business number
// replaces the temporary testing one. Each element is optional -- only
// the landing page has the card, only the other five pages have the
// footer link -- so this silently no-ops wherever an element isn't
// present, same guard style loadCollections above already uses.
function initWhatsAppLinks() {
  // Both open the existing chat widget (window.CakeCraftChat.open(), see
  // chat-widget.js) -- the contact card's "Start Chat" button and the
  // hero's own secondary CTA (Final Landing Page Polish). Two separate
  // id-based blocks, not a shared selector, so the already-approved
  // contact card above needs no attribute changes of its own.
  const chatCard = document.getElementById("talkToUsChatBtn");
  if (chatCard) {
    chatCard.addEventListener("click", () => {
      if (window.CakeCraftChat) window.CakeCraftChat.open();
    });
  }

  const heroChatBtn = document.getElementById("heroChatBtn");
  if (heroChatBtn) {
    heroChatBtn.addEventListener("click", () => {
      if (window.CakeCraftChat) window.CakeCraftChat.open();
    });
  }

  const landingLink = document.getElementById("talkToUsWhatsAppLink");
  if (landingLink) {
    landingLink.href = buildWhatsAppLink();
  }

  const footerLink = document.getElementById("footerWhatsAppLink");
  if (footerLink) {
    footerLink.href = buildWhatsAppLink();
  }

  // Servings + Event Pricing: the Designer's Custom Event notice (76+
  // guests) reuses this exact same link, only present on designer.html.
  const customEventLink = document.getElementById("customEventWhatsAppLink");
  if (customEventLink) {
    customEventLink.href = buildWhatsAppLink();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initNavToggle();
  initFooterYear();
  loadCollections();
  initWhatsAppLinks();
});
