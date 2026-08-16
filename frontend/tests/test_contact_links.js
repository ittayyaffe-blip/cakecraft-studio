// Regression coverage for the "Custom Event Flow Repair" contact-wiring
// fixes: (1) the WhatsApp integration link pointed at a personal number
// instead of the Twilio Sandbox destination, (2) mailto: links had no
// target="_blank", so clicking Email handed off the whole tab to Gmail
// and lost the CakeCraft page. No test framework/new dependency -- runs
// the ACTUAL shipped chat-widget.js (via `vm`) and reads the ACTUAL
// shipped HTML files directly (no DOM needed for plain markup checks).
// Run from `frontend/`:
//
//     node tests/test_contact_links.js

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const TWILIO_SANDBOX_NUMBER = "14155238886";
const FOOTER_CONTACT_NUMBER = "972545446601";

// Every customer-facing page that has the site footer (all of them) plus
// designer.html's Custom Event box and index.html's "Talk to us" card --
// i.e. every mailto: occurrence in the project (verified via grep before
// writing this list).
const HTML_FILES = [
  "index.html",
  "designer.html",
  "order-review.html",
  "customer-information.html",
  "payment.html",
  "confirmation.html",
  "templates.html",
];

function loadChatWidget() {
  // Only buildWhatsAppLink() (a pure top-level function, hoisted) is
  // under test here -- initChatWidget() itself only ever runs from a
  // DOMContentLoaded listener, so leaving that a no-op avoids needing to
  // build a full widget DOM for a link-format check.
  const sandbox = { document: { addEventListener: () => {} }, console };
  vm.createContext(sandbox);
  const code = fs.readFileSync(path.join(__dirname, "..", "js", "chat-widget.js"), "utf8");
  vm.runInContext(code, sandbox, { filename: "chat-widget.js" });
  return sandbox;
}

// --- Part 8, items 13/14: WhatsApp Custom Event CTA destination ----------

function test_whatsapp_link_targets_the_twilio_sandbox_number() {
  const { buildWhatsAppLink } = loadChatWidget();
  const link = buildWhatsAppLink();
  if (!link.includes(TWILIO_SANDBOX_NUMBER)) {
    throw new Error(`expected the Twilio Sandbox number ${TWILIO_SANDBOX_NUMBER} in the link, got: ${link}`);
  }
}

function test_whatsapp_link_does_not_target_the_personal_contact_number() {
  const { buildWhatsAppLink } = loadChatWidget();
  const link = buildWhatsAppLink();
  if (link.includes(FOOTER_CONTACT_NUMBER)) {
    throw new Error(`REGRESSION: WhatsApp link must not target the personal/footer contact number, got: ${link}`);
  }
}

// customEventWhatsAppLink (designer.html and order-review.html) is wired
// up by app.js's initWhatsAppLinks() via document.getElementById(...).href
// = buildWhatsAppLink() -- the same shared function, so no separate check
// of its destination is needed; this instead confirms the id is actually
// present on both pages for that wiring to find.
function test_custom_event_whatsapp_link_element_exists_on_designer_and_order_review() {
  ["designer.html", "order-review.html"].forEach((file) => {
    const html = fs.readFileSync(path.join(__dirname, "..", file), "utf8");
    if (!html.includes('id="customEventWhatsAppLink"')) {
      throw new Error(`${file}: missing id="customEventWhatsAppLink" for app.js's initWhatsAppLinks() to wire up`);
    }
  });
}

// --- Part 8, item 12: Email contact preserves the CakeCraft browser context

function test_every_mailto_link_has_target_blank_and_noopener() {
  HTML_FILES.forEach((file) => {
    const html = fs.readFileSync(path.join(__dirname, "..", file), "utf8");
    const mailtoAnchors = html.match(/<a\s[^>]*href="mailto:mybestcake2002@gmail\.com"[^>]*>/g) || [];
    if (mailtoAnchors.length === 0) throw new Error(`${file}: expected at least one mailto: anchor`);
    mailtoAnchors.forEach((tag) => {
      if (!tag.includes('target="_blank"')) throw new Error(`${file}: mailto anchor missing target="_blank" -- clicking Email would lose the CakeCraft page: ${tag}`);
      if (!tag.includes('rel="noopener noreferrer"')) throw new Error(`${file}: mailto anchor missing rel="noopener noreferrer": ${tag}`);
    });
  });
}

// --- Part 9: the footer/contact phone must NOT be touched by this repair -

function test_footer_contact_phone_number_is_unchanged() {
  HTML_FILES.forEach((file) => {
    const html = fs.readFileSync(path.join(__dirname, "..", file), "utf8");
    if (!html.includes(`href="tel:+972545446601"`)) {
      throw new Error(`${file}: footer contact phone number changed or missing -- Part 9 requires it stay untouched`);
    }
  });
}

function run() {
  const tests = Object.entries({
    test_whatsapp_link_targets_the_twilio_sandbox_number,
    test_whatsapp_link_does_not_target_the_personal_contact_number,
    test_custom_event_whatsapp_link_element_exists_on_designer_and_order_review,
    test_every_mailto_link_has_target_blank_and_noopener,
    test_footer_contact_phone_number_is_unchanged,
  });
  let failed = 0;
  for (const [name, fn] of tests) {
    try {
      fn();
      console.log(`OK  ${name}`);
    } catch (err) {
      failed += 1;
      console.log(`FAIL ${name}: ${err.message}`);
    }
  }
  console.log(`\n${tests.length - failed}/${tests.length} checks passed.`);
  if (failed > 0) process.exit(1);
}

run();
