// Regression coverage for the "Serving Guide + Custom Event UX Fix" --
// entering a Custom Event guest count (76+) left the previously-selected
// standard cake size (e.g. "Small") visually checked. No test
// framework/new dependency -- this project's frontend has never had one --
// so this is a small, dependency-free Node script that runs the ACTUAL
// shipped pricing.js/summary.js/validation.js/designer.js (via `vm`, not a
// reimplementation) against a minimal fake DOM covering only the handful
// of element/event operations those files actually touch. Run from
// `frontend/`:
//
//     node tests/test_designer_serving_guide.js

const fs = require("fs");
const path = require("path");
const vm = require("vm");

// --- Minimal fake DOM ----------------------------------------------------
// One element class covers every node designer.js creates or looks up
// (div/fieldset/label/input/button/span/p/ul/li) -- radios get a
// `checked` setter that enforces native same-name mutual exclusion
// (browsers do this for real, whether the `checked` flip comes from a
// user click or from script), and `querySelector` supports exactly the
// two selector shapes the real designer.js ever asks for:
// `input[name="X"][value="Y"]` and `input[name="X"]:checked`.

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.parentNode = null;
    this._listeners = {};
    this._classSet = new Set();
    this.type = "";
    this.name = "";
    this.value = "";
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this._checked = false;
    this._radioRegistry = null; // set by createElement(), only for <input>
  }

  get checked() {
    return this._checked;
  }

  set checked(val) {
    this._checked = !!val;
    if (this._checked && this.type === "radio" && this.name && this._radioRegistry) {
      this._radioRegistry.forEach((other) => {
        if (other !== this && other.type === "radio" && other.name === this.name) other._checked = false;
      });
    }
  }

  get classList() {
    const set = this._classSet;
    return { add: (c) => set.add(c), remove: (c) => set.delete(c), contains: (c) => set.has(c) };
  }

  set innerHTML(html) {
    if (html === "") this.children = []; // the only value the real code ever assigns
  }

  get innerHTML() {
    return "";
  }

  setAttribute() {}

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  append(...nodes) {
    nodes.forEach((n) => {
      if (n && n.tagName) this.appendChild(n); // bare strings (text nodes) aren't asserted on
    });
  }

  addEventListener(type, handler) {
    (this._listeners[type] = this._listeners[type] || []).push(handler);
  }

  fire(type) {
    (this._listeners[type] || []).forEach((h) => h());
  }

  dispatchEvent(event) {
    if (!event.target) event.target = this;
    (this._listeners[event.type] || []).forEach((h) => h(event));
    if (event.bubbles && this.parentNode) this.parentNode.dispatchEvent(event);
    return true;
  }

  querySelector(selector) {
    const nameMatch = selector.match(/\[name="([^"]+)"\]/);
    const valueMatch = selector.match(/\[value="([^"]+)"\]/);
    const checkedOnly = selector.includes(":checked");
    const results = [];
    const walk = (el) => {
      if (el.tagName === "input") results.push(el);
      el.children.forEach(walk);
    };
    walk(this);
    return (
      results.find((el) => {
        if (nameMatch && el.name !== nameMatch[1]) return false;
        if (valueMatch && el.value !== valueMatch[1]) return false;
        if (checkedOnly && !el.checked) return false;
        return true;
      }) || null
    );
  }
}

class FakeEvent {
  constructor(type, opts = {}) {
    this.type = type;
    this.bubbles = !!opts.bubbles;
    this.target = null;
  }
}

// Real designer.js gates on `input instanceof HTMLInputElement` --
// Symbol.hasInstance lets that check mean the same thing here (tagName
// "input") without a second element class.
class HTMLInputElementMarker {
  static [Symbol.hasInstance](obj) {
    return !!obj && obj.tagName === "input";
  }
}

// --- Fixture ---------------------------------------------------------------

const CAKE_SIZES = [
  { id: "small-id", name: "Small", price_adjustment: 0, servings_min: 8, servings_max: 12 },
  { id: "medium-id", name: "Medium", price_adjustment: 50, servings_min: 13, servings_max: 20 },
  { id: "large-id", name: "Large", price_adjustment: 100, servings_min: 21, servings_max: 30 },
  { id: "xl-id", name: "XL", price_adjustment: 150, servings_min: 31, servings_max: 50 },
  { id: "event-id", name: "Event", price_adjustment: 200, servings_min: 51, servings_max: 75 },
];

async function loadPage() {
  const allRadios = [];
  const makeEl = (tag) => new FakeElement(tag);

  const elements = {
    guestCount: makeEl("input"),
    guestCountRecommendation: makeEl("p"),
    designerOptionsContainer: makeEl("div"),
    customEventNotice: makeEl("div"),
    customEventMessage: makeEl("p"),
    startDesigningBtn: makeEl("button"),
    currentPrice: makeEl("span"),
    servingRange: makeEl("span"),
    summaryTemplateName: makeEl("span"),
    summaryCakeSize: makeEl("span"),
    summaryFlavor: makeEl("span"),
    summaryFilling: makeEl("span"),
    summaryFrosting: makeEl("span"),
    validationStatus: makeEl("p"),
    validationMissingList: makeEl("ul"),
  };
  elements.guestCountRecommendation.hidden = true;
  elements.customEventNotice.hidden = true;

  const documentStub = {
    getElementById: (id) => elements[id] || null,
    createElement: (tag) => {
      const el = new FakeElement(tag);
      if (tag === "input") {
        el._radioRegistry = allRadios;
        allRadios.push(el);
      }
      return el;
    },
    addEventListener: (type, handler) => {
      if (type === "DOMContentLoaded") handler();
    },
  };

  const sandbox = {
    document: documentStub,
    window: { location: { search: "?id=tpl-1" } },
    URLSearchParams,
    Event: FakeEvent,
    HTMLInputElement: HTMLInputElementMarker,
    getDesignerInit: async () => ({
      template: { id: "tpl-1", name: "Vanilla Dream", category: "Birthday", style: "Modern", base_price: 40, preview_image: null },
      options: {
        cake_sizes: CAKE_SIZES,
        flavors: [{ id: "flavor-1", name: "Vanilla" }],
        fillings: [{ id: "filling-1", name: "Vanilla Buttercream" }],
        frostings: [{ id: "frosting-1", name: "Vanilla Buttercream" }],
      },
    }),
    console,
  };
  vm.createContext(sandbox);

  ["pricing.js", "summary.js", "validation.js", "designer.js"].forEach((file) => {
    const code = fs.readFileSync(path.join(__dirname, "..", "js", file), "utf8");
    vm.runInContext(code, sandbox, { filename: file });
  });

  // loadDesigner() is async (awaits getDesignerInit) and DOMContentLoaded's
  // handler doesn't await it -- flush pending microtasks so the option
  // radios exist before any test touches them.
  await new Promise((resolve) => setImmediate(resolve));

  return { elements, sandbox };
}

function setGuestCount(elements, n) {
  elements.guestCount.value = String(n);
  elements.guestCount.fire("input");
}

function selectNonSizeOptions(elements) {
  ["flavor", "filling", "frosting"].forEach((name) => {
    const radio = elements.designerOptionsContainer.querySelector(`input[name="${name}"]`);
    if (!radio) throw new Error(`fixture missing a ${name} option to select`);
    radio.checked = true;
    radio.dispatchEvent(new FakeEvent("change", { bubbles: true }));
  });
}

function checkedSizeRadio(elements) {
  return elements.designerOptionsContainer.querySelector('input[name="cake_size"]:checked');
}

function expectSelectedSize(elements, sizeId, sizeName) {
  const checked = checkedSizeRadio(elements);
  if (!checked || checked.value !== sizeId) {
    throw new Error(`expected ${sizeName} (${sizeId}) selected, got ${checked ? checked.value : "none"}`);
  }
  if (elements.summaryCakeSize.textContent !== sizeName) {
    throw new Error(`expected summary size "${sizeName}", got "${elements.summaryCakeSize.textContent}"`);
  }
}

function expectNoStandardSizeSelected(elements) {
  const checked = checkedSizeRadio(elements);
  if (checked) throw new Error(`expected no size selected, but ${checked.value} is checked`);
  if (elements.summaryCakeSize.textContent !== "Not selected") {
    throw new Error(`expected summary size "Not selected", got "${elements.summaryCakeSize.textContent}"`);
  }
}

// --- Tests -----------------------------------------------------------------

async function test_01_guest_count_10_selects_small() {
  const { elements } = await loadPage();
  setGuestCount(elements, 10);
  expectSelectedSize(elements, "small-id", "Small");
}

async function test_02_guest_count_15_selects_medium() {
  const { elements } = await loadPage();
  setGuestCount(elements, 15);
  expectSelectedSize(elements, "medium-id", "Medium");
}

async function test_03_guest_count_25_selects_large() {
  const { elements } = await loadPage();
  setGuestCount(elements, 25);
  expectSelectedSize(elements, "large-id", "Large");
}

async function test_04_guest_count_45_selects_xl() {
  const { elements } = await loadPage();
  setGuestCount(elements, 45);
  expectSelectedSize(elements, "xl-id", "XL");
}

async function test_05_guest_count_70_selects_event() {
  const { elements } = await loadPage();
  setGuestCount(elements, 70);
  expectSelectedSize(elements, "event-id", "Event");
}

async function test_06_guest_count_76_clears_selection_and_shows_custom_event() {
  const { elements } = await loadPage();
  setGuestCount(elements, 45); // pre-select XL so the clear is actually exercised
  expectSelectedSize(elements, "xl-id", "XL");
  setGuestCount(elements, 76);
  expectNoStandardSizeSelected(elements);
  if (elements.customEventNotice.hidden) throw new Error("expected Custom Event notice visible at 76 guests");
}

async function test_07_guest_count_100_clears_selection_and_shows_custom_event() {
  const { elements } = await loadPage();
  setGuestCount(elements, 10); // pre-select Small so the clear is actually exercised
  expectSelectedSize(elements, "small-id", "Small");
  setGuestCount(elements, 100);
  expectNoStandardSizeSelected(elements);
  if (elements.customEventNotice.hidden) throw new Error("expected Custom Event notice visible at 100 guests");
}

async function test_08_returning_from_100_to_45_selects_xl() {
  const { elements } = await loadPage();
  selectNonSizeOptions(elements);
  setGuestCount(elements, 100);
  expectNoStandardSizeSelected(elements);
  setGuestCount(elements, 45);
  expectSelectedSize(elements, "xl-id", "XL");
  if (elements.startDesigningBtn.hidden) throw new Error("expected Continue visible again at 45 guests");
  if (elements.startDesigningBtn.disabled) throw new Error("expected Continue enabled again at 45 guests");
}

async function test_09_going_from_45_to_100_clears_selection() {
  const { elements } = await loadPage();
  setGuestCount(elements, 45);
  expectSelectedSize(elements, "xl-id", "XL");
  setGuestCount(elements, 100);
  expectNoStandardSizeSelected(elements);
}

async function test_10_continue_hidden_for_76_plus() {
  const { elements } = await loadPage();
  selectNonSizeOptions(elements);
  setGuestCount(elements, 76);
  if (!elements.startDesigningBtn.hidden) throw new Error("expected Continue hidden at 76 guests");
}

async function test_11_continue_restored_for_valid_le_75() {
  const { elements } = await loadPage();
  selectNonSizeOptions(elements);
  setGuestCount(elements, 76);
  if (!elements.startDesigningBtn.hidden) throw new Error("sanity check failed: expected hidden at 76 guests");
  setGuestCount(elements, 25);
  if (elements.startDesigningBtn.hidden) throw new Error("expected Continue visible again at 25 guests");
  if (elements.startDesigningBtn.disabled) throw new Error("expected Continue enabled again at 25 guests");
}

function test_12_serving_guide_contains_all_six_ranges() {
  const html = fs.readFileSync(path.join(__dirname, "..", "designer.html"), "utf8");
  const expected = ["8–12", "13–20", "21–30", "31–50", "51–75", "76+", "Small", "Medium", "Large", "XL", "Event", "Custom Event"];
  expected.forEach((token) => {
    if (!html.includes(token)) throw new Error(`serving guide missing "${token}"`);
  });
}

// Bonus: item 5's "manual conflicting selection" rule -- not in the
// numbered TESTS list, but real branch logic was added for it above, so
// it gets its own check per "lazy code without its check is unfinished."
async function test_13_manual_conflicting_size_click_snaps_back_to_recommended() {
  const { elements } = await loadPage();
  setGuestCount(elements, 45); // recommends XL
  expectSelectedSize(elements, "xl-id", "XL");

  const smallRadio = elements.designerOptionsContainer.querySelector('input[name="cake_size"][value="small-id"]');
  smallRadio.checked = true;
  smallRadio.dispatchEvent(new FakeEvent("change", { bubbles: true }));

  expectSelectedSize(elements, "xl-id", "XL"); // snapped back, never left on Small
}

async function run() {
  const tests = Object.entries({
    test_01_guest_count_10_selects_small,
    test_02_guest_count_15_selects_medium,
    test_03_guest_count_25_selects_large,
    test_04_guest_count_45_selects_xl,
    test_05_guest_count_70_selects_event,
    test_06_guest_count_76_clears_selection_and_shows_custom_event,
    test_07_guest_count_100_clears_selection_and_shows_custom_event,
    test_08_returning_from_100_to_45_selects_xl,
    test_09_going_from_45_to_100_clears_selection,
    test_10_continue_hidden_for_76_plus,
    test_11_continue_restored_for_valid_le_75,
    test_12_serving_guide_contains_all_six_ranges,
    test_13_manual_conflicting_size_click_snaps_back_to_recommended,
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
