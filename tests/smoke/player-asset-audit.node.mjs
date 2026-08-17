import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { auditPlayerAssetPresence, resolvePlayerAssetUrls } from "./routes.cjs";

const CAST_ROUTE = "/systems/demo/";
const NON_CAST_ROUTE = "/about/";

// resolvePlayerAssetUrls takes a manifest file directly (release-resources.json
// for a production build, local-asset-map.json for the loopback build
// check-site.sh's own browser gate serves) rather than an output directory with
// a hardcoded filename - the browser gate crashed with ENOENT until this was
// fixed, since release-resources.json is production-only and never exists
// beside the loopback build (see routes.cjs's resolvePlayerAssetUrls comment).
// These fixtures pin that contract at the manifest-schema level, independent
// of any real site build.
function manifestFixture(overrides = {}) {
  return {
    schema_version: 3,
    resource_count: 2,
    resources: [
      {
        logical_path: "vendor/asciinema/asciinema-player.css",
        output_path: "a/aa.css",
        request_url: "/a/aa.css",
      },
      {
        logical_path: "vendor/asciinema/asciinema-player.min.js",
        output_path: "a/bb.js",
        request_url: "/a/bb.js",
      },
    ],
    ...overrides,
  };
}

function withManifest(manifest, fn) {
  const dir = mkdtempSync(path.join(tmpdir(), "player-asset-manifest-"));
  const manifestPath = path.join(dir, "manifest.json");
  try {
    writeFileSync(manifestPath, JSON.stringify(manifest));
    return fn(manifestPath);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("resolvePlayerAssetUrls resolves the pair from a manifest file's own resources array", () => {
  withManifest(manifestFixture(), (manifestPath) => {
    assert.deepEqual(resolvePlayerAssetUrls(manifestPath), {
      cssUrl: "/a/aa.css",
      jsUrl: "/a/bb.js",
    });
  });
});

test("resolvePlayerAssetUrls throws when the manifest omits the player asset pair", () => {
  withManifest(manifestFixture({ resources: [] }), (manifestPath) => {
    assert.throws(() => resolvePlayerAssetUrls(manifestPath), /does not resolve the asciinema player asset pair/);
  });
});

test("resolvePlayerAssetUrls throws (does not silently pass) when the manifest file is absent", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "player-asset-manifest-"));
  try {
    assert.throws(() => resolvePlayerAssetUrls(path.join(dir, "release-resources.json")), /ENOENT/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

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
