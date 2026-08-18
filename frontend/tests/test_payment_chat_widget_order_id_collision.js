// Regression coverage for the payment-page order-id collision bug:
// payment.js, confirmation.js, and chat-widget.js each declared their own
// global (non-module, `defer`) function named getOrderIdFromUrl(). Loaded
// together on the same page, the LAST <script> tag's declaration silently
// overwrites the earlier ones in the shared global scope. On payment.html
// (script order: api.js, app.js, payment.js, chat-widget.js) chat-widget.js
// loaded last and its version read the wrong query param ("orderId"
// instead of payment.js's own "order"), so payment.html could never read
// its own order reference -- "No order reference was provided." for every
// real customer.
//
// Fix: chat-widget.js's helper renamed to getChatOrderIdFromUrl() (its own
// call site updated to match) -- payment.js and confirmation.js keep their
// own getOrderIdFromUrl() unchanged, no longer at risk of being clobbered
// regardless of <script> tag order. No business behavior changed anywhere.
//
// No test framework/new dependency -- runs the ACTUAL shipped JS files
// (via `vm`), same convention as this project's other frontend tests. Run
// from `frontend/`:
//
//     node tests/test_payment_chat_widget_order_id_collision.js

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function readJs(name) {
  return fs.readFileSync(path.join(__dirname, "..", "js", name), "utf8");
}

// Runs one or more script sources in a single shared global context, same
// as a real page's sequential <script defer> execution -- a later script's
// top-level `function foo(){}` overwrites an earlier same-named one.
function runScriptsInSharedContext(scriptSources, search) {
  const sandbox = {
    window: {},
    document: { addEventListener: () => {} }, // no-op: skips each file's own DOMContentLoaded-triggered init
    URLSearchParams,
    console,
  };
  sandbox.window.location = { search, pathname: "/payment.html" };
  // Scripts reference the bare global `window`/`document` (browser globals),
  // not `sandbox.window` -- expose them as the context's own globals too.
  vm.createContext(sandbox);
  vm.runInContext("window.document = document;", sandbox);
  scriptSources.forEach((code, i) => vm.runInContext(code, sandbox, { filename: `script${i}.js` }));
  return sandbox;
}

// --- 1. payment.html with ?order=<id> uses payment.js's own order parser -

function test_payment_page_order_id_parser_survives_chat_widget_load_order() {
  const sandbox = runScriptsInSharedContext(
    [readJs("payment.js"), readJs("chat-widget.js")],
    "?order=hero-order-123"
  );
  const result = vm.runInContext("getOrderIdFromUrl()", sandbox);
  if (result !== "hero-order-123") {
    throw new Error(
      `REGRESSION: payment.html's getOrderIdFromUrl() should read the "order" param and return ` +
      `"hero-order-123", got: ${JSON.stringify(result)}`
    );
  }
}

// --- 2. chat-widget.js no longer overwrites payment.js's helper ----------

function test_chat_widget_no_longer_declares_the_colliding_global_name() {
  const code = readJs("chat-widget.js");
  if (/function\s+getOrderIdFromUrl\s*\(/.test(code)) {
    throw new Error("REGRESSION: chat-widget.js must not declare a global getOrderIdFromUrl() -- rename it (e.g. getChatOrderIdFromUrl) to avoid colliding with payment.js/confirmation.js");
  }
  if (!/function\s+getChatOrderIdFromUrl\s*\(/.test(code)) {
    throw new Error("chat-widget.js is missing its own uniquely-named getChatOrderIdFromUrl() helper");
  }
}

// --- 3. chat widget still reads its intended orderId parameter -----------

function test_chat_widget_still_reads_its_own_orderId_param() {
  const sandbox = runScriptsInSharedContext([readJs("chat-widget.js")], "?orderId=chat-order-456");
  const result = vm.runInContext("getChatOrderIdFromUrl()", sandbox);
  if (result !== "chat-order-456") {
    throw new Error(`chat-widget.js's getChatOrderIdFromUrl() should read the "orderId" param and return "chat-order-456", got: ${JSON.stringify(result)}`);
  }
}

// --- 4. confirmation page behavior remains unchanged ----------------------

function test_confirmation_page_order_id_parser_unaffected() {
  const sandbox = runScriptsInSharedContext(
    [readJs("confirmation.js"), readJs("chat-widget.js")],
    "?orderId=confirmed-order-789"
  );
  const result = vm.runInContext("getOrderIdFromUrl()", sandbox);
  if (result !== "confirmed-order-789") {
    throw new Error(
      `REGRESSION: confirmation.html's getOrderIdFromUrl() should read the "orderId" param and return ` +
      `"confirmed-order-789", got: ${JSON.stringify(result)}`
    );
  }
}

// --- 5. existing customer-order flow remains unaffected -------------------
// payment.js's own "order" contract and confirmation.js's own "orderId"
// contract are exactly as they were before this fix -- only chat-widget.js
// changed. A source-text check that neither file's query-param key moved.

function test_payment_and_confirmation_query_param_contracts_unchanged() {
  const paymentCode = readJs("payment.js");
  if (!/getOrderIdFromUrl[\s\S]*?\.get\("order"\)/.test(paymentCode)) {
    throw new Error('REGRESSION: payment.js must still read the "order" query param -- its contract must not change as part of this fix');
  }
  const confirmationCode = readJs("confirmation.js");
  if (!/getOrderIdFromUrl[\s\S]*?\.get\("orderId"\)/.test(confirmationCode)) {
    throw new Error('REGRESSION: confirmation.js must still read the "orderId" query param -- its contract must not change as part of this fix');
  }
}

function run() {
  const tests = Object.entries({
    test_payment_page_order_id_parser_survives_chat_widget_load_order,
    test_chat_widget_no_longer_declares_the_colliding_global_name,
    test_chat_widget_still_reads_its_own_orderId_param,
    test_confirmation_page_order_id_parser_unaffected,
    test_payment_and_confirmation_query_param_contracts_unchanged,
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
