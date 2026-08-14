import assert from "node:assert/strict";
import test from "node:test";

import { auditPlayerAssetPresence } from "./routes.cjs";

const CAST_ROUTE = "/systems/demo/";
const NON_CAST_ROUTE = "/about/";

function present(route, isCastRoute) {
  return {
    route,
    isCastRoute,
    cssMarkupCount: 1,
    jsMarkupCount: 1,
    cssRequestCount: 1,
    jsRequestCount: 1,
  };
}

function absent(route, isCastRoute) {
  return {
    route,
    isCastRoute,
    cssMarkupCount: 0,
    jsMarkupCount: 0,
    cssRequestCount: 0,
    jsRequestCount: 0,
  };
}

test("a cast route with the exact pair present in markup and requests passes clean", () => {
  assert.deepEqual(auditPlayerAssetPresence(present(CAST_ROUTE, true)), []);
});

test("a non-cast route with neither asset in markup or requests passes clean", () => {
  assert.deepEqual(auditPlayerAssetPresence(absent(NON_CAST_ROUTE, false)), []);
});

for (const signal of ["cssMarkupCount", "cssRequestCount", "jsMarkupCount", "jsRequestCount"]) {
  test(`leaking ${signal} onto a non-cast route fails closed`, () => {
    const fixture = { ...absent(NON_CAST_ROUTE, false), [signal]: 1 };
    const violations = auditPlayerAssetPresence(fixture);
    assert.equal(violations.length, 1, violations.join("; "));
    assert.match(violations[0], new RegExp(`found 1`));
  });

  test(`omitting ${signal} from a cast route fails closed`, () => {
    const fixture = { ...present(CAST_ROUTE, true), [signal]: 0 };
    const violations = auditPlayerAssetPresence(fixture);
    assert.equal(violations.length, 1, violations.join("; "));
    assert.match(violations[0], new RegExp(`found 0`));
  });
}
