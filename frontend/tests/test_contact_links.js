// Regression coverage for contact-wiring across two rounds of fixes:
// (1) Custom Event Flow Repair -- the general WhatsApp integration link
// (buildWhatsAppLink(), used by the footer/landing/chat entry points)
// pointed at a personal number instead of the Twilio Sandbox destination,
// and mailto: links had no target="_blank", handing off the whole tab to
// Gmail. (2) Final Stabilization -- the Custom Event (>75 guests) human
// escalation box specifically must NOT use WhatsApp/Twilio at all; it
// offers the phone/service number + email instead. No test framework/new
// dependency -- runs the ACTUAL shipped chat-widget.js (via `vm`) and
// reads the ACTUAL shipped HTML files directly (no DOM needed for plain
// markup checks). Run from `frontend/`:
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

// --- Final Stabilization, Part F: chat widget large-event notice ---------
// Purely a hardcoded string with no branching logic, so a source-text
// check is the right-sized test -- no need to execute initChatWidget()'s
// full DOM-building just to verify one static message.

function test_chat_widget_shows_the_large_event_notice_with_the_service_phone_number() {
  const code = fs.readFileSync(path.join(__dirname, "..", "js", "chat-widget.js"), "utf8");
  const noticeMatch = code.match(/largeEventNotice\.textContent =\s*([\s\S]*?);/);
  if (!noticeMatch) throw new Error("chat-widget.js missing the large-event (>75 guests) notice text");
  const notice = noticeMatch[1];
  if (!notice.includes("Planning a larger celebration")) {
    throw new Error("large-event notice missing its opening line");
  }
  if (!notice.includes("+972 54-544-6601")) {
    throw new Error("large-event notice missing the service phone number");
  }
  if (notice.includes(TWILIO_SANDBOX_NUMBER)) {
    throw new Error("REGRESSION: large-event notice must not reference the Twilio Sandbox number");
  }
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

// Final Stabilization: Custom Event (>75 guests) human escalation is
// PHONE + EMAIL only -- the Twilio Sandbox is a technical/demo
// integration, not the customer-service destination for a tailored
// proposal (Part C explicitly reverses the earlier "reuse buildWhatsAppLink()
// everywhere" decision for this one box). Checks the Custom Event notice
// box specifically, not just "the page somewhere" -- a tel: link exists
// elsewhere too (the footer), so this greps the box's own markup only.
function test_custom_event_notice_offers_phone_and_email_not_whatsapp() {
  ["designer.html", "order-review.html"].forEach((file) => {
    const html = fs.readFileSync(path.join(__dirname, "..", file), "utf8");
    const boxMatch = html.match(/<div id="customEventNotice"[\s\S]*?<\/div>/);
    if (!boxMatch) throw new Error(`${file}: customEventNotice box not found`);
    const box = boxMatch[0];
    if (!box.includes(`href="tel:+${FOOTER_CONTACT_NUMBER}"`)) {
      throw new Error(`${file}: Custom Event box missing the phone/service number link`);
    }
    if (!box.includes('href="mailto:mybestcake2002@gmail.com"')) {
      throw new Error(`${file}: Custom Event box missing the email link`);
    }
    if (box.includes("wa.me") || box.includes("WhatsApp") || box.includes(TWILIO_SANDBOX_NUMBER)) {
      throw new Error(`${file}: REGRESSION -- Custom Event box must not offer WhatsApp/Twilio Sandbox as the escalation path`);
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
    test_custom_event_notice_offers_phone_and_email_not_whatsapp,
    test_every_mailto_link_has_target_blank_and_noopener,
    test_footer_contact_phone_number_is_unchanged,
    test_chat_widget_shows_the_large_event_notice_with_the_service_phone_number,
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
