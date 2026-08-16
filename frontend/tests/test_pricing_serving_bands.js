// Regression/coverage for Servings + Event Pricing's client-side
// recommendation display (pricing.js's getRecommendedBand, validation.js's
// customEvent handling). Same "no test framework, run the actual shipped
// file via vm" approach as test_customer_information_pickup.js. Run from
// `frontend/`:
//
//     node tests/test_pricing_serving_bands.js

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadModules(...files) {
  const sandbox = { console };
  vm.createContext(sandbox);
  files.forEach((file) => {
    const code = fs.readFileSync(path.join(__dirname, "..", "js", file), "utf8");
    vm.runInContext(code, sandbox, { filename: file });
  });
  return sandbox;
}

function test_recommended_band_matches_every_boundary() {
  const { getRecommendedBand } = loadModules("pricing.js");
  const cases = [
    [10, "SMALL"], [12, "SMALL"], [13, "MEDIUM"], [20, "MEDIUM"],
    [21, "LARGE"], [30, "LARGE"], [31, "XL"], [50, "XL"],
    [51, "EVENT"], [75, "EVENT"], [76, "CUSTOM_EVENT"], [100, "CUSTOM_EVENT"],
  ];
  cases.forEach(([guests, expectedBand]) => {
    const result = getRecommendedBand(guests);
    if (!result || result.band !== expectedBand) {
      throw new Error(`${guests} guests -> expected ${expectedBand}, got ${result && result.band}`);
    }
  });
}

function test_recommended_band_null_for_invalid_input() {
  const { getRecommendedBand } = loadModules("pricing.js");
  [0, -5, 3.5, NaN].forEach((bad) => {
    if (getRecommendedBand(bad) !== null) throw new Error(`expected null for ${bad}`);
  });
}

function test_validate_order_requires_guest_count() {
  const { validateOrder } = loadModules("pricing.js", "validation.js");
  const state = { template: {}, cakeSize: {}, flavor: {}, filling: {}, frosting: {}, guestCount: null };
  const result = validateOrder(state);
  if (result.valid) throw new Error("expected invalid without a guest count");
  if (!result.missing.includes("Number of Guests")) throw new Error("expected 'Number of Guests' in missing list");
}

function test_validate_order_blocks_76_plus_as_custom_event_not_missing() {
  const { validateOrder } = loadModules("pricing.js", "validation.js");
  const state = { template: {}, cakeSize: {}, flavor: {}, filling: {}, frosting: {}, guestCount: 100 };
  const result = validateOrder(state);
  if (result.valid) throw new Error("expected invalid for 100 guests");
  if (!result.customEvent) throw new Error("expected customEvent=true for 100 guests");
  if (result.missing.includes("Number of Guests")) {
    throw new Error("100 guests is stated, not missing -- customEvent is the correct reason, not 'missing'");
  }
}

function test_validate_order_valid_for_a_complete_standard_order() {
  const { validateOrder } = loadModules("pricing.js", "validation.js");
  const state = {
    template: { id: "t1" }, cakeSize: { id: "s1" }, flavor: { id: "f1" },
    filling: { id: "fl1" }, frosting: { id: "fr1" }, guestCount: 20,
  };
  const result = validateOrder(state);
  if (!result.valid) throw new Error(`expected valid, got missing=${JSON.stringify(result.missing)} customEvent=${result.customEvent}`);
}

function run() {
  const tests = {
    test_recommended_band_matches_every_boundary,
    test_recommended_band_null_for_invalid_input,
    test_validate_order_requires_guest_count,
    test_validate_order_blocks_76_plus_as_custom_event_not_missing,
    test_validate_order_valid_for_a_complete_standard_order,
  };
  let failed = 0;
  for (const [name, fn] of Object.entries(tests)) {
    try {
      fn();
      console.log(`OK  ${name}`);
    } catch (err) {
      failed += 1;
      console.log(`FAIL ${name}: ${err.message}`);
    }
  }
  console.log(`\n${Object.keys(tests).length - failed}/${Object.keys(tests).length} checks passed.`);
  if (failed > 0) process.exit(1);
}

run();
