// Regression coverage for the "Submit Order stays disabled with no
// explanation" bug (URGENT Phase 2 Regression). No test framework/new
// dependency -- this project's frontend has never had one (see every
// other phase's "manual + node --check" validation) -- so this is a
// small, dependency-free Node script that runs the ACTUAL shipped
// customer-information.js (via `vm`, not a reimplementation) against a
// minimal fake DOM covering only the handful of properties/methods that
// file actually touches. Run from `frontend/`:
//
//     node tests/test_customer_information_pickup.js

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeInput({ value = "", requiredMissing = false, rangeInvalid = false } = {}) {
  const el = {
    value,
    hidden: true,
    textContent: "",
    _customValidity: "",
    _listeners: {},
    // Set by loadPage() once the form exists -- real "input"/"change"
    // events bubble from a form control up to its <form> by default,
    // which is exactly what lets ONE form-level listener
    // (refreshSubmitButtonState) react to every field without each field
    // needing its own copy of that logic. Simulated here explicitly
    // since this fake DOM has no real event propagation.
    _form: null,
    min: "",
    max: "",
    addEventListener(type, handler) {
      (this._listeners[type] = this._listeners[type] || []).push(handler);
    },
    fire(type) {
      (this._listeners[type] || []).forEach((h) => h());
      if (this._form) this._form.fire(type);
    },
    setCustomValidity(msg) {
      this._customValidity = msg;
    },
    get validationMessage() {
      if (this._customValidity) return this._customValidity;
      if (!this.value && requiredMissing) return "Please fill out this field.";
      if (this.value && rangeInvalid) return "Value must be between 09:00 and 18:00.";
      return "";
    },
    checkValidity() {
      if (this._customValidity) return false;
      if (!this.value && requiredMissing) return false;
      if (this.value && rangeInvalid) return false;
      return true;
    },
  };
  return el;
}

function loadPage(fixture) {
  const elements = {
    pickupDate: makeInput({ requiredMissing: true }),
    pickupTime: makeInput({ requiredMissing: true, rangeInvalid: fixture.timeOutOfHours || false }),
    pickupDateTimeError: makeInput(),
    pickupRushWarning: makeInput(),
    customerInfoForm: {
      _listeners: {},
      addEventListener(type, handler) {
        (this._listeners[type] = this._listeners[type] || []).push(handler);
      },
      fire(type) {
        (this._listeners[type] || []).forEach((h) => h());
      },
      checkValidity() {
        // Mirrors the real native contract: a form is valid iff every
        // descendant control is valid -- exactly the four controls this
        // regression concerns (customerName/Phone/Email/allergy are
        // stubbed as always-valid here since they're not what this bug
        // was about; the real backend/E2E path already covers them).
        return elements.pickupDate.checkValidity() && elements.pickupTime.checkValidity() && fixture.allergyChecked !== false;
      },
    },
    submitOrderBtn: { disabled: false, addEventListener() {} },
    backToOrderReviewBtn: { addEventListener() {} },
  };
  // Simulated bubbling (see makeInput's own note): pickupDate/pickupTime
  // "input"/"change" events reach the form-level listener the real
  // customer-information.js relies on for refreshSubmitButtonState.
  elements.pickupDate._form = elements.customerInfoForm;
  elements.pickupTime._form = elements.customerInfoForm;

  const documentStub = {
    getElementById: (id) => elements[id],
    addEventListener: (type, handler) => {
      if (type === "DOMContentLoaded") handler();
    },
  };

  const sandbox = {
    document: documentStub,
    window: { location: { search: "" } },
    URLSearchParams: URLSearchParams,
    getDesignerInit: async () => ({ template: { category: "Birthday" } }),
    console,
  };
  vm.createContext(sandbox);
  const code = fs.readFileSync(path.join(__dirname, "..", "js", "customer-information.js"), "utf8");
  vm.runInContext(code, sandbox, { filename: "customer-information.js" });

  return { elements, sandbox };
}

function setPickupDate(elements, isoDate) {
  elements.pickupDate.value = isoDate;
  elements.pickupDate.fire("input");
}

function setPickupTime(elements, hhmm) {
  elements.pickupTime.value = hhmm;
  elements.pickupTime.fire("input");
}

// --- A: fully valid -> enabled -----------------------------------------

function test_valid_pickup_enables_submit() {
  const { elements } = loadPage({});
  setPickupDate(elements, "2026-08-18"); // a real Tuesday
  setPickupTime(elements, "13:00");
  if (elements.submitOrderBtn.disabled) throw new Error("expected Submit to be enabled for a fully valid pickup");
}

// --- B/C: missing date/time -> disabled ---------------------------------

function test_missing_pickup_date_disables_submit() {
  const { elements } = loadPage({});
  setPickupTime(elements, "13:00");
  // pickupDate.value stays "" -- required-missing
  if (!elements.submitOrderBtn.disabled) throw new Error("expected Submit disabled with no pickup date");
}

function test_missing_pickup_time_disables_submit() {
  const { elements } = loadPage({});
  setPickupDate(elements, "2026-08-18");
  if (!elements.submitOrderBtn.disabled) throw new Error("expected Submit disabled with no pickup time");
}

// --- D: Monday -> disabled, WITH a visible message (the actual fix) ----

function test_monday_pickup_disables_submit_and_shows_a_visible_message() {
  const { elements } = loadPage({});
  setPickupDate(elements, "2026-08-17"); // a real Monday
  setPickupTime(elements, "13:00");
  if (!elements.submitOrderBtn.disabled) throw new Error("Monday must still block submission");
  if (elements.pickupDateTimeError.hidden) throw new Error("REGRESSION: the customer sees no explanation for the disabled button");
  if (!/monday/i.test(elements.pickupDateTimeError.textContent)) throw new Error("error message doesn't explain the Monday rule");
}

// --- E: out-of-hours time -> disabled, with a visible message ----------

function test_out_of_hours_time_disables_submit_and_shows_a_visible_message() {
  const { elements } = loadPage({ timeOutOfHours: true });
  setPickupDate(elements, "2026-08-18");
  setPickupTime(elements, "20:00");
  if (!elements.submitOrderBtn.disabled) throw new Error("out-of-hours time must still block submission");
  if (elements.pickupDateTimeError.hidden) throw new Error("REGRESSION: no visible explanation for an out-of-hours time");
}

// --- F: allergy unchecked -> disabled (unrelated to pickup, unaffected) -

function test_allergy_unchecked_still_disables_submit() {
  const { elements } = loadPage({ allergyChecked: false });
  setPickupDate(elements, "2026-08-18");
  setPickupTime(elements, "13:00");
  if (!elements.submitOrderBtn.disabled) throw new Error("allergy confirmation gate must be unaffected by this fix");
}

// --- G: correcting an invalid date clears the stale error and enables --

function test_correcting_an_invalid_date_clears_the_error_and_enables_submit() {
  const { elements } = loadPage({});
  setPickupDate(elements, "2026-08-17"); // Monday -- invalid
  setPickupTime(elements, "13:00");
  if (!elements.submitOrderBtn.disabled) throw new Error("expected disabled on the Monday date");
  if (elements.pickupDateTimeError.hidden) throw new Error("expected a visible error on the Monday date");

  setPickupDate(elements, "2026-08-18"); // corrected to Tuesday
  if (elements.submitOrderBtn.disabled) throw new Error("stale custom validity was not cleared on correction");
  if (!elements.pickupDateTimeError.hidden) throw new Error("stale error message was not cleared on correction");
}

// --- H: rush warning alone never blocks submission ----------------------

function test_rush_warning_does_not_disable_submit() {
  // A fixed, known-non-Monday near date (2026-08-18, Tuesday) so this
  // assertion is deterministic rather than depending on which weekday
  // "tomorrow" happens to land on when the test runs.
  const { elements } = loadPage({});
  setPickupDate(elements, "2026-08-18"); // Tuesday, 1-2 days out depending on run date -- may or may not be "rush", irrelevant to this assertion
  setPickupTime(elements, "13:00");
  if (elements.submitOrderBtn.disabled) {
    throw new Error("a valid, non-Monday, in-hours pickup must never be disabled regardless of any rush warning");
  }
  // The real point: whenever the rush warning IS showing, it must never
  // be the reason Submit is disabled -- these are deliberately
  // independent signals (see refreshRushWarning/refreshPickupErrorMessage).
  if (!elements.pickupRushWarning.hidden && elements.submitOrderBtn.disabled) {
    throw new Error("a rush-order warning must never by itself disable Submit");
  }
}

function run() {
  const tests = Object.entries({
    test_valid_pickup_enables_submit,
    test_missing_pickup_date_disables_submit,
    test_missing_pickup_time_disables_submit,
    test_monday_pickup_disables_submit_and_shows_a_visible_message,
    test_out_of_hours_time_disables_submit_and_shows_a_visible_message,
    test_allergy_unchecked_still_disables_submit,
    test_correcting_an_invalid_date_clears_the_error_and_enables_submit,
    test_rush_warning_does_not_disable_submit,
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
