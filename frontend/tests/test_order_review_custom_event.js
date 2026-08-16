// Regression coverage for order-review.js's Custom Event route/state
// guard (URGENT Custom Event Flow Repair, Part 3) -- guest count is now
// authoritative on this page too, exactly like the Designer and the
// backend's create_order(). Before this fix, order-review.js never even
// read guestCount from the URL, so a stale/manually-edited cakeSize
// param could present a standard size/price as a valid order for a
// 76+-guest event (and, independently, Continue was permanently disabled
// for every order since "Number of Guests" was always "missing").
// No test framework/new dependency -- runs the ACTUAL shipped
// pricing.js/summary.js/validation.js/order-review.js via `vm`. Run from
// `frontend/`:
//
//     node tests/test_order_review_custom_event.js

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeElement() {
  const classes = new Set();
  return {
    _textContent: "",
    // Real DOM coerces textContent to a string on write (order-review.js
    // writes a raw number for guest count) -- match that instead of
    // letting assertions accidentally compare a number to a string.
    get textContent() {
      return this._textContent;
    },
    set textContent(val) {
      this._textContent = val == null ? "" : String(val);
    },
    hidden: false,
    disabled: false,
    src: "",
    alt: "",
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c) },
    _listeners: {},
    addEventListener(type, handler) {
      (this._listeners[type] = this._listeners[type] || []).push(handler);
    },
    click() {
      (this._listeners.click || []).forEach((h) => h());
    },
  };
}

const CAKE_SIZES = [
  { id: "small-id", name: "Small", price_adjustment: 0, servings_min: 8, servings_max: 12 },
  { id: "medium-id", name: "Medium", price_adjustment: 50, servings_min: 13, servings_max: 20 },
  { id: "large-id", name: "Large", price_adjustment: 100, servings_min: 21, servings_max: 30 },
  { id: "xl-id", name: "XL", price_adjustment: 150, servings_min: 31, servings_max: 50 },
  { id: "event-id", name: "Event", price_adjustment: 200, servings_min: 51, servings_max: 75 },
];
const FLAVORS = [{ id: "flavor-1", name: "Vanilla" }];
const FILLINGS = [{ id: "filling-1", name: "Vanilla Buttercream" }];
const FROSTINGS = [{ id: "frosting-1", name: "Vanilla Buttercream" }];

async function loadOrderReviewPage(search) {
  const elements = {
    reviewTemplateImage: makeElement(),
    reviewTemplateName: makeElement(),
    reviewGuestCount: makeElement(),
    reviewCakeSize: makeElement(),
    reviewFlavor: makeElement(),
    reviewFilling: makeElement(),
    reviewFrosting: makeElement(),
    reviewPrice: makeElement(),
    reviewServingRange: makeElement(),
    continueToCustomerInfoBtn: makeElement(),
    reviewStandardDetails: makeElement(),
    customEventNotice: makeElement(),
    customEventMessage: makeElement(),
    reviewImageWrap: makeElement(),
    reviewDetails: makeElement(),
    returnToDesignerBtn: makeElement(),
  };
  elements.continueToCustomerInfoBtn.disabled = true;
  elements.customEventNotice.hidden = true;

  const documentStub = {
    getElementById: (id) => elements[id] || null,
    addEventListener: (type, handler) => {
      if (type === "DOMContentLoaded") handler();
    },
  };

  const sandbox = {
    document: documentStub,
    window: { location: { search } },
    URLSearchParams,
    getDesignerInit: async () => ({
      template: { id: "tpl-1", name: "Vanilla Dream", preview_image: null, base_price: 40 },
      options: { cake_sizes: CAKE_SIZES, flavors: FLAVORS, fillings: FILLINGS, frostings: FROSTINGS },
    }),
    console,
  };
  vm.createContext(sandbox);

  ["pricing.js", "summary.js", "validation.js", "order-review.js"].forEach((file) => {
    const code = fs.readFileSync(path.join(__dirname, "..", "js", file), "utf8");
    vm.runInContext(code, sandbox, { filename: file });
  });

  // loadOrderReview() is async -- flush pending microtasks before any
  // assertion touches the rendered elements.
  await new Promise((resolve) => setImmediate(resolve));

  return { elements };
}

function validOrderQuery(overrides = {}) {
  const params = new URLSearchParams({
    id: "tpl-1",
    cakeSize: "small-id", // deliberately wrong/irrelevant when guestCount is present -- guestCount must win
    flavor: "flavor-1",
    filling: "filling-1",
    frosting: "frosting-1",
    ...overrides,
  });
  return `?${params.toString()}`;
}

// --- Part 8, item 1: 75 -> Event -> standard price shown -> Continue allowed

async function test_75_guests_shows_event_size_and_standard_price_continue_allowed() {
  const { elements } = await loadOrderReviewPage(validOrderQuery({ guestCount: "75" }));
  if (elements.reviewCakeSize.textContent !== "Event") throw new Error(`expected Event, got "${elements.reviewCakeSize.textContent}"`);
  if (elements.reviewPrice.textContent !== "$240.00") throw new Error(`expected $240.00 (40 base + 200 Event), got "${elements.reviewPrice.textContent}"`);
  if (elements.customEventNotice.hidden !== true) throw new Error("expected Custom Event notice hidden at 75 guests");
  if (elements.continueToCustomerInfoBtn.hidden) throw new Error("expected Continue visible at 75 guests");
  if (elements.continueToCustomerInfoBtn.disabled) throw new Error("expected Continue enabled at 75 guests");
}

// --- Part 8, items 2/3: 76 and 100 -> Custom Event -> no standard price ---

async function test_76_guests_shows_no_standard_price() {
  const { elements } = await loadOrderReviewPage(validOrderQuery({ guestCount: "76" }));
  if (elements.reviewStandardDetails.hidden !== true) throw new Error("REGRESSION: standard details (size/price) still shown at 76 guests");
  if (elements.reviewPrice.textContent !== "") throw new Error(`expected no price ever written at 76 guests, got "${elements.reviewPrice.textContent}"`);
  if (elements.customEventNotice.hidden) throw new Error("expected Custom Event notice visible at 76 guests");
}

async function test_100_guests_shows_no_standard_price() {
  const { elements } = await loadOrderReviewPage(validOrderQuery({ guestCount: "100" }));
  if (elements.reviewStandardDetails.hidden !== true) throw new Error("REGRESSION: standard details (size/price) still shown at 100 guests");
  if (elements.reviewPrice.textContent !== "") throw new Error(`expected no price ever written at 100 guests, got "${elements.reviewPrice.textContent}"`);
}

// --- Part 8, item 7 / bug report item 5: the actual reported scenario ----
// (URL says cakeSize=medium-id -- e.g. a customer who manually picked
// Medium before the guest count changed, or a tampered/stale query
// param -- while guestCount=100. Order Review must never present this
// as a valid 100-guest order.)

async function test_100_guests_cannot_present_a_stale_medium_size_as_valid() {
  const { elements } = await loadOrderReviewPage(validOrderQuery({ guestCount: "100", cakeSize: "medium-id" }));
  if (elements.reviewCakeSize.textContent === "Medium") throw new Error("REGRESSION: Order Review presented Medium as valid for a 100-guest order");
  if (elements.reviewPrice.textContent !== "") throw new Error(`expected no price for the mismatched 100-guest/Medium combination, got "${elements.reviewPrice.textContent}"`);
  if (!elements.continueToCustomerInfoBtn.disabled) throw new Error("REGRESSION: Continue must not be enabled for a 100-guest Custom Event");
  if (!elements.continueToCustomerInfoBtn.hidden) throw new Error("expected Continue hidden for a 100-guest Custom Event");
}

// --- Part 7 / report item 11: the 45-guest path end-to-end -----------------

async function test_45_guests_shows_xl_correct_price_and_enables_continue() {
  const { elements } = await loadOrderReviewPage(validOrderQuery({ guestCount: "45" }));
  if (elements.reviewGuestCount.textContent !== "45") throw new Error(`expected Guests: 45, got "${elements.reviewGuestCount.textContent}"`);
  if (elements.reviewCakeSize.textContent !== "XL") throw new Error(`expected XL, got "${elements.reviewCakeSize.textContent}"`);
  if (elements.reviewPrice.textContent !== "$190.00") throw new Error(`expected $190.00 (40 base + 150 XL), got "${elements.reviewPrice.textContent}"`);
  if (elements.reviewServingRange.textContent !== "31–50 servings") throw new Error(`expected 31–50 servings, got "${elements.reviewServingRange.textContent}"`);
  if (elements.continueToCustomerInfoBtn.hidden) throw new Error("expected Continue visible at 45 guests");
  if (elements.continueToCustomerInfoBtn.disabled) throw new Error("expected Continue enabled at 45 guests -- this was the silent-disable regression");
}

async function run() {
  const tests = Object.entries({
    test_75_guests_shows_event_size_and_standard_price_continue_allowed,
    test_76_guests_shows_no_standard_price,
    test_100_guests_shows_no_standard_price,
    test_100_guests_cannot_present_a_stale_medium_size_as_valid,
    test_45_guests_shows_xl_correct_price_and_enables_continue,
  });
  let failed = 0;
  for (const [name, fn] of tests) {
    try {
      await fn();
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
