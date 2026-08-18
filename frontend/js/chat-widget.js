// CakeCraft Studio — floating chat widget, present on every customer-
// facing page (loaded via one shared <script> tag, not duplicated markup
// per page). Reuses the existing AI Agent through POST /chat/ask (see
// api.js's askChat) — this file only builds/renders the widget and talks
// to that one endpoint, same "API calls in api.js, rendering here" split
// every other customer-facing page already follows. Chat-assisted
// ordering (POST /chat/order, api.js's askChatOrder) is the same widget,
// same transcript, just a second endpoint the composer routes to once
// the customer opts in — see the "ordering mode" state below.
//
// Identity (name + email) and the visible transcript are kept in
// sessionStorage — not because this project uses client-side storage
// elsewhere (it doesn't, every other page passes state via the URL), but
// because a chat that forgot who you were and everything you'd asked the
// moment you clicked to the next page wouldn't feel like one conversation
// at all. Scoped to the browser tab/session, not persisted beyond it.
//
// Ordering mode itself (orderingMode/orderDraft below) is deliberately
// NOT persisted to sessionStorage, unlike identity/history -- this
// project's chat/order endpoint is stateless per turn by design (the
// draft round-trips through the request/response), and a page reload
// mid-order is a rare enough edge case that the minimal, honest MVP
// behavior (reload = back to plain Q&A, the transcript so far still
// visible) is preferable to the extra state-restoration complexity of
// persisting "was I mid-order" across a reload too.

const CHAT_IDENTITY_KEY = "cakecraft_chat_identity";
const CHAT_HISTORY_KEY = "cakecraft_chat_history";
const CHAT_LANDING_INTRO =
  "Have a question before you order? Ask us about ingredients, allergies, dietary preferences, or special requirements.";
const CHAT_GENERIC_INTRO = "Have a question? Ask us about ingredients, allergies, dietary preferences, or anything else.";

// The Twilio WhatsApp Sandbox number -- the ONE place it lives. This is
// a university project's Twilio Sandbox integration, not a real CakeCraft
// WhatsApp Business number: it's the only WhatsApp destination the
// backend webhook can actually receive and answer. Do NOT point this at
// the footer/contact phone (+972 54 544 6601) -- that's a different
// number for a different purpose (see designer.html's serving-guide era
// bug report). Swap this single constant if/when a real WhatsApp
// Business number replaces the Sandbox; nothing else in this file needs
// to change. Digits only, no "+"/spaces (wa.me's required format).
const WHATSAPP_NUMBER = "14155238886";
// The ONE authoritative prefill text -- every customer-facing WhatsApp
// entry point (landing page card, footer link, hero CTA) calls
// buildWhatsAppLink() below rather than constructing its own wa.me URL,
// so there is exactly one place this string is ever set (confirmed: no
// other caller in this project builds a wa.me link independently). A
// previously reported "duplicated message" was the text appearing twice
// in WhatsApp's own compose box -- that's wa.me prefill appending to an
// already-unsent draft left in the chat from an earlier click, on
// WhatsApp's side, not something a URL/text change here can control; a
// single fixed source (already true) is the correct fix on this end.
const WHATSAPP_PREFILL_MESSAGE = "Hi CakeCraft Studio! I'd like some help with a cake.";

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

// Named distinctly from payment.js's/confirmation.js's own same-purpose
// helpers -- all three are classic (non-module) scripts sharing one global
// scope, so an identically-named function here would silently overwrite
// (or be overwritten by) theirs depending on <script> tag order. This one
// is chat-widget's own: it reads the *chat* grounding param ("orderId"),
// unrelated to payment.js's "order" query param contract.
function getChatOrderIdFromUrl() {
  return new URLSearchParams(window.location.search).get("orderId");
}

// Website First (see agent_service._website_collection_link) means an AI
// reply can now genuinely contain a real CakeCraft link the customer
// should be able to click -- built with createElement/textContent for
// each piece, never innerHTML with the raw AI text, matching this
// project's existing "no innerHTML + interpolation" convention (see
// e.g. admin-notifications.js's own top note) so nothing the model
// writes can ever be interpreted as markup.
const _URL_PATTERN = /(https?:\/\/[^\s]+)/g;

function appendTextWithLinks(container, text) {
  const parts = text.split(_URL_PATTERN);
  parts.forEach((part) => {
    if (/^https?:\/\//.test(part)) {
      const link = document.createElement("a");
      link.href = part;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = part;
      container.appendChild(link);
    } else if (part) {
      container.appendChild(document.createTextNode(part));
    }
  });
}

// Shown the instant a question/order message is sent, removed the
// instant a real response (or error) arrives -- so a Claude call that
// takes a few seconds never reads as a frozen page. Not part of the
// persisted transcript (never passed to appendChatHistory), same as
// buildOrderNudge/buildPayNowButton below.
function buildThinkingIndicator() {
  const bubble = document.createElement("div");
  bubble.className = "chat-widget__bubble chat-widget__bubble--assistant chat-widget__bubble--thinking";
  bubble.textContent = "Thinking…";
  // Visually transient without touching the stylesheet -- this bubble
  // never outlives one request, so a one-off inline style is simpler
  // than adding a new CSS rule for it.
  bubble.style.opacity = "0.7";
  bubble.style.fontStyle = "italic";
  return bubble;
}

function buildMessageBubble(role, text) {
  const bubble = document.createElement("div");
  bubble.className =
    role === "customer"
      ? "chat-widget__bubble chat-widget__bubble--customer"
      : role === "order-success"
        ? "chat-widget__bubble chat-widget__bubble--order-success"
        : "chat-widget__bubble chat-widget__bubble--assistant";
  appendTextWithLinks(bubble, text);
  return bubble;
}

// The "Start an order?" nudge shown under an assistant reply whose
// intent came back NEW_ORDER_INQUIRY (see ChatAskResponse.intent's own
// note) -- a plain button, not part of the persisted transcript
// (appendChatHistory only ever stores {role, text} bubbles), so it
// simply doesn't reappear on a stored-history re-render, which is the
// right behavior: it's an offer for *this* reply, not a permanent
// transcript entry.
function buildOrderNudge(onStart) {
  const nudge = document.createElement("button");
  nudge.type = "button";
  nudge.className = "chat-widget__order-nudge";
  nudge.textContent = "Start an order";
  nudge.addEventListener("click", onStart);
  return nudge;
}

// Shown once, right after a chat-assisted order is created (status
// "pending") -- payment is a separate, explicit customer action from
// order confirmation (see agent_service.run_order_assistant_turn's own
// note), never triggered automatically. Same plain-button pattern as
// buildOrderNudge above, not part of the persisted transcript.
function buildPayNowButton(onPay) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "chat-widget__order-nudge";
  button.textContent = "Pay Now (Simulated)";
  button.addEventListener("click", onPay);
  return button;
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

  // Final Stabilization: a warm, always-visible heads-up at the top of
  // every chat -- the deterministic >75 gate in run_order_assistant_turn
  // (backend) remains the actual enforcement; this is purely so a large-
  // event customer doesn't have to discover the limit by first typing out
  // their whole request.
  const largeEventNotice = document.createElement("p");
  largeEventNotice.className = "chat-widget__large-event-notice";
  largeEventNotice.textContent =
    "Planning a larger celebration? 🎂 For events with more than 75 guests, we'd love to create " +
    "something especially for you. Please contact our service team directly at +972 54-544-6601 for a " +
    "tailored cake and pricing proposal.";

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

  panel.append(header, intro, largeEventNotice, messages, errorEl, composer);

  // Chat-assisted ordering MVP: once true, composer submissions go to
  // sendOrderMessage (POST /chat/order) instead of sendQuestion (POST
  // /chat/ask) -- see this file's own top note on why this is plain JS
  // state, not sessionStorage. orderDraft is exactly the ChatOrderDraft
  // shape the backend returns/expects; null means "nothing collected
  // yet" (the very first order-assistant turn).
  let orderingMode = false;
  let orderDraft = null;
  // The ONE customer message that triggered the "Start an order" nudge --
  // sent once, on the very first /chat/order call only, so the assistant
  // can try mapping something like "for 20 people" to a real size without
  // asking again (see ChatOrderRequest.triggerContext's own note). Not a
  // broader history import: cleared immediately after that first send.
  let orderTriggerContext = null;
  // Set the instant sendQuestion/sendOrderMessage starts, cleared in
  // their own `finally` -- the composer's submit handler checks this
  // before starting a new request, so a duplicate Send (double-click,
  // Enter spam) while one is already pending is a no-op instead of
  // firing a second overlapping request.
  let requestInFlight = false;

  const startOrderingMode = (triggerMessage) => {
    orderingMode = true;
    orderDraft = null;
    orderTriggerContext = triggerMessage || null;
    questionInput.placeholder = "Tell me what you'd like to order…";
    questionInput.focus();
    // Fire the first order-assistant turn immediately, reusing the exact
    // message that triggered this nudge (already visible as a customer
    // bubble from the Q&A turn -- `silent` skips re-appending it) so the
    // customer sees ordering mode actually respond instead of a dead
    // button click. Same endpoint/draft/triggerContext plumbing as every
    // later turn, just invoked here instead of waiting for a composer
    // submit.
    if (triggerMessage) {
      sendOrderMessage(triggerMessage, { silent: true });
    }
  };

  const exitOrderingMode = () => {
    orderingMode = false;
    orderDraft = null;
    orderTriggerContext = null;
    questionInput.placeholder = "Ask a question...";
  };

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
    requestInFlight = true;
    const thinkingBubble = buildThinkingIndicator();
    messages.appendChild(thinkingBubble);
    messages.scrollTop = messages.scrollHeight;

    try {
      const response = await askChat({
        name: identity.name,
        email: identity.email,
        question,
        orderId: getChatOrderIdFromUrl() || undefined,
      });
      thinkingBubble.remove();
      messages.appendChild(buildMessageBubble("assistant", response.answer));
      appendChatHistory({ role: "assistant", text: response.answer });
      // Chat-assisted ordering MVP: offer to start collecting an order
      // only when the AI's own existing intent classification says so,
      // and only if we're not already mid-order -- never automatic,
      // the customer always has to click this.
      if (response.intent === "NEW_ORDER_INQUIRY" && !orderingMode) {
        messages.appendChild(buildOrderNudge(() => startOrderingMode(question)));
      }
      messages.scrollTop = messages.scrollHeight;
    } catch (error) {
      thinkingBubble.remove();
      errorEl.textContent =
        error && error.message === "Request timed out"
          ? "That's taking longer than expected — please try again."
          : "Sorry, something went wrong. Please try again.";
      errorEl.classList.remove("is-hidden");
    } finally {
      sendBtn.disabled = false;
      requestInFlight = false;
    }
  };

  // Simulated/demo payment -- the customer's own explicit click, calling
  // POST /orders/{id}/pay directly (never through Claude/the order
  // assistant, so payment success can never be an AI-generated claim --
  // see payment_service.simulate_payment's own docstring). Rendered text
  // comes entirely from the real backend response.
  const handlePayNow = async (orderId, button) => {
    if (button.disabled) return; // already processing -- blocks a duplicate click
    button.disabled = true;
    button.textContent = "Processing payment…";
    errorEl.classList.add("is-hidden");

    try {
      const result = await payOrder(orderId);
      const text =
        `Thank you! 🎂\n\nPayment successful — your CakeCraft order is confirmed.\n\n` +
        `Order: #${orderId}\nTotal paid: $${Number(result.amount).toFixed(2)}\n\n` +
        `We'll keep you updated as your cake moves through preparation.`;
      messages.appendChild(buildMessageBubble("order-success", text));
      appendChatHistory({ role: "order-success", text });
      button.remove();
    } catch (error) {
      // Payment is idempotent server-side (see payOrder's own note) --
      // safe to simply let the customer try again; a retry either
      // completes the same payment or, if it already went through,
      // returns that same result rather than charging (simulated) twice.
      errorEl.textContent =
        error && error.message === "Request timed out"
          ? "Payment is taking longer than expected. It's safe to try again."
          : "Sorry, something went wrong processing payment. Please try again.";
      errorEl.classList.remove("is-hidden");
      button.disabled = false;
      button.textContent = "Pay Now (Simulated)";
    }
    messages.scrollTop = messages.scrollHeight;
  };

  // One turn of chat-assisted ordering (POST /chat/order) -- same
  // transcript/history as sendQuestion above, just a different endpoint
  // and it tracks orderDraft between turns. Never creates an order
  // itself; that's entirely agent_service.run_order_assistant_turn's
  // decision, gated on the customer's own explicit confirmation (see
  // that function's docstring) -- this only renders whatever it decided.
  const sendOrderMessage = async (message, { silent = false } = {}) => {
    const identity = getChatIdentity();
    // `silent` is only ever true for the auto-fired first turn from
    // startOrderingMode above -- that message is already on screen from
    // the Q&A turn that earned the "Start an order" nudge, so re-adding
    // it here would show the customer's own words twice.
    if (!silent) {
      messages.appendChild(buildMessageBubble("customer", message));
      appendChatHistory({ role: "customer", text: message });
      messages.scrollTop = messages.scrollHeight;
    }
    errorEl.classList.add("is-hidden");
    sendBtn.disabled = true;
    requestInFlight = true;
    const thinkingBubble = buildThinkingIndicator();
    messages.appendChild(thinkingBubble);
    messages.scrollTop = messages.scrollHeight;

    // Only ever sent on the first order-assistant turn (see
    // startOrderingMode) -- cleared immediately regardless of outcome so
    // a retry after an error doesn't resend stale context.
    const triggerContext = orderTriggerContext;
    orderTriggerContext = null;

    try {
      const response = await askChatOrder({
        name: identity.name,
        email: identity.email,
        message,
        draft: orderDraft,
        triggerContext: triggerContext || undefined,
      });
      thinkingBubble.remove();
      orderDraft = response.draft;

      if (response.orderCreated) {
        messages.appendChild(buildMessageBubble("order-success", response.reply));
        appendChatHistory({ role: "order-success", text: response.reply });
        if (response.orderId) {
          const payBtn = buildPayNowButton(() => handlePayNow(response.orderId, payBtn));
          messages.appendChild(payBtn);
        }
        exitOrderingMode();
      } else {
        messages.appendChild(buildMessageBubble("assistant", response.reply));
        appendChatHistory({ role: "assistant", text: response.reply });
      }
      messages.scrollTop = messages.scrollHeight;
    } catch (error) {
      thinkingBubble.remove();
      errorEl.textContent =
        error && error.message === "Request timed out"
          ? "That's taking longer than expected — please try again."
          : "Sorry, something went wrong. Please try again.";
      errorEl.classList.remove("is-hidden");
    } finally {
      sendBtn.disabled = false;
      requestInFlight = false;
    }
  };

  composer.addEventListener("submit", (event) => {
    event.preventDefault();
    if (requestInFlight) return;
    const text = questionInput.value.trim();
    if (!text) return;
    questionInput.value = "";
    if (orderingMode) {
      sendOrderMessage(text);
    } else {
      sendQuestion(text);
    }
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
