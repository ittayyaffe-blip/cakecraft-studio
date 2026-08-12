// CakeCraft Studio — floating chat widget, present on every customer-
// facing page (loaded via one shared <script> tag, not duplicated markup
// per page). Reuses the existing AI Agent through POST /chat/ask (see
// api.js's askChat) — this file only builds/renders the widget and talks
// to that one endpoint, same "API calls in api.js, rendering here" split
// every other customer-facing page already follows.
//
// Identity (name + email) and the visible transcript are kept in
// sessionStorage — not because this project uses client-side storage
// elsewhere (it doesn't, every other page passes state via the URL), but
// because a chat that forgot who you were and everything you'd asked the
// moment you clicked to the next page wouldn't feel like one conversation
// at all. Scoped to the browser tab/session, not persisted beyond it.

const CHAT_IDENTITY_KEY = "cakecraft_chat_identity";
const CHAT_HISTORY_KEY = "cakecraft_chat_history";
const CHAT_LANDING_INTRO =
  "Have a question before you order? Ask us about ingredients, allergies, dietary preferences, or special requirements.";
const CHAT_GENERIC_INTRO = "Have a question? Ask us about ingredients, allergies, dietary preferences, or anything else.";

// Temporary testing number -- the ONE place it lives. Swap this single
// constant for the real CakeCraft Studio WhatsApp Business number once
// it's available; nothing else in this file needs to change. Digits
// only, no "+"/spaces (wa.me's required format).
const WHATSAPP_NUMBER = "972545446601";
const WHATSAPP_PREFILL_MESSAGE = "Hi CakeCraft Studio! I'd like to ask a question about a cake.";

function buildWhatsAppLink() {
  return `https://wa.me/${WHATSAPP_NUMBER}?text=${encodeURIComponent(WHATSAPP_PREFILL_MESSAGE)}`;
}

function getChatIdentity() {
  try {
    const raw = sessionStorage.getItem(CHAT_IDENTITY_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    return null;
  }
}

function setChatIdentity(identity) {
  sessionStorage.setItem(CHAT_IDENTITY_KEY, JSON.stringify(identity));
}

function getChatHistory() {
  try {
    const raw = sessionStorage.getItem(CHAT_HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (error) {
    return [];
  }
}

function appendChatHistory(entry) {
  const history = getChatHistory();
  history.push(entry);
  sessionStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(history));
  return history;
}

function isLandingPage() {
  const path = window.location.pathname;
  return path === "/" || path.endsWith("/index.html") || path === "";
}

function getOrderIdFromUrl() {
  return new URLSearchParams(window.location.search).get("orderId");
}

function buildMessageBubble(role, text) {
  const bubble = document.createElement("div");
  bubble.className = role === "customer" ? "chat-widget__bubble chat-widget__bubble--customer" : "chat-widget__bubble chat-widget__bubble--assistant";
  bubble.textContent = text;
  return bubble;
}

function buildIdentityForm(onSubmit) {
  const form = document.createElement("form");
  form.className = "chat-widget__identity-form";

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.placeholder = "Your name";
  nameInput.required = true;
  nameInput.setAttribute("aria-label", "Your name");

  const emailInput = document.createElement("input");
  emailInput.type = "email";
  emailInput.placeholder = "Your email";
  emailInput.required = true;
  emailInput.setAttribute("aria-label", "Your email");

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.className = "btn btn-primary chat-widget__identity-submit";
  submitBtn.textContent = "Start chat";

  form.append(nameInput, emailInput, submitBtn);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = nameInput.value.trim();
    const email = emailInput.value.trim();
    if (!name || !email) return;
    onSubmit({ name, email });
  });

  return form;
}

function initChatWidget() {
  const introText = isLandingPage() ? CHAT_LANDING_INTRO : CHAT_GENERIC_INTRO;

  const toggleBtn = document.createElement("button");
  toggleBtn.type = "button";
  toggleBtn.className = "chat-widget__toggle";
  toggleBtn.setAttribute("aria-label", "Open chat");
  toggleBtn.textContent = "Chat with us";

  const panel = document.createElement("div");
  panel.className = "chat-widget__panel is-hidden";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "CakeCraft Studio chat");

  const header = document.createElement("div");
  header.className = "chat-widget__header";
  const headerTitle = document.createElement("span");
  headerTitle.textContent = "CakeCraft Studio";
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "chat-widget__close";
  closeBtn.setAttribute("aria-label", "Close chat");
  closeBtn.textContent = "×";
  header.append(headerTitle, closeBtn);

  const intro = document.createElement("p");
  intro.className = "chat-widget__intro";
  intro.textContent = introText;

  const messages = document.createElement("div");
  messages.className = "chat-widget__messages";

  const errorEl = document.createElement("p");
  errorEl.className = "admin-state admin-state--error is-hidden chat-widget__error";
  errorEl.setAttribute("role", "alert");

  const composer = document.createElement("form");
  composer.className = "chat-widget__composer is-hidden";
  const questionInput = document.createElement("input");
  questionInput.type = "text";
  questionInput.placeholder = "Ask a question...";
  questionInput.setAttribute("aria-label", "Your question");
  const sendBtn = document.createElement("button");
  sendBtn.type = "submit";
  sendBtn.className = "btn btn-primary";
  sendBtn.textContent = "Send";
  composer.append(questionInput, sendBtn);

  panel.append(header, intro, messages, errorEl, composer);

  const renderStoredHistory = () => {
    getChatHistory().forEach((entry) => messages.appendChild(buildMessageBubble(entry.role, entry.text)));
    messages.scrollTop = messages.scrollHeight;
  };

  const showComposer = () => {
    const identityForm = panel.querySelector(".chat-widget__identity-form");
    if (identityForm) identityForm.remove();
    composer.classList.remove("is-hidden");
    renderStoredHistory();
  };

  const sendQuestion = async (question) => {
    const identity = getChatIdentity();
    messages.appendChild(buildMessageBubble("customer", question));
    appendChatHistory({ role: "customer", text: question });
    messages.scrollTop = messages.scrollHeight;
    errorEl.classList.add("is-hidden");
    sendBtn.disabled = true;

    try {
      const response = await askChat({
        name: identity.name,
        email: identity.email,
        question,
        orderId: getOrderIdFromUrl() || undefined,
      });
      messages.appendChild(buildMessageBubble("assistant", response.answer));
      appendChatHistory({ role: "assistant", text: response.answer });
      messages.scrollTop = messages.scrollHeight;
    } catch (error) {
      errorEl.textContent = "Sorry, something went wrong. Please try again.";
      errorEl.classList.remove("is-hidden");
    } finally {
      sendBtn.disabled = false;
    }
  };

  composer.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = questionInput.value.trim();
    if (!question) return;
    questionInput.value = "";
    sendQuestion(question);
  });

  const identity = getChatIdentity();
  if (identity) {
    showComposer();
  } else {
    panel.insertBefore(
      buildIdentityForm((newIdentity) => {
        setChatIdentity(newIdentity);
        showComposer();
      }),
      messages
    );
  }

  toggleBtn.addEventListener("click", () => {
    panel.classList.toggle("is-hidden");
    if (!panel.classList.contains("is-hidden")) {
      questionInput.focus();
    }
  });
  closeBtn.addEventListener("click", () => panel.classList.add("is-hidden"));

  document.body.append(toggleBtn, panel);

  // Lets other on-page entry points (the landing page's "Chat with us"
  // card, see app.js) open this same widget/conversation instead of
  // building a second one -- WhatsApp is independently discoverable now
  // (no longer inside this panel), but "Chat with us" still just opens
  // this exact widget.
  window.CakeCraftChat = {
    open: () => {
      panel.classList.remove("is-hidden");
      questionInput.focus();
    },
  };
}

document.addEventListener("DOMContentLoaded", initChatWidget);
