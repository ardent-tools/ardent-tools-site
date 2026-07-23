import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


const functionUrl = new URL("../../functions/[[path]].js", import.meta.url);
const source = await readFile(functionUrl);
const moduleUrl = `data:text/javascript;base64,${source.toString("base64")}`;
const { onRequest } = await import(moduleUrl);
const SPECULATION_DIGEST = "1".repeat(64);
const SPECULATION_URL = `/a/${SPECULATION_DIGEST}.json`;

const EXPECTED_DIRECT_HEADERS = Object.freeze({
  "cache-control": "no-store, no-transform",
  "strict-transport-security": "max-age=31536000; includeSubDomains; preload",
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
  "referrer-policy": "strict-origin-when-cross-origin",
  "permissions-policy": "accelerometer=(), browsing-topics=(), camera=(), clipboard-read=(), clipboard-write=(), geolocation=(), gyroscope=(), hid=(), magnetometer=(), microphone=(), midi=(), payment=(), serial=(), usb=(), web-share=(), xr-spatial-tracking=()",
  "content-security-policy": "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; manifest-src 'self'; worker-src 'none'; upgrade-insecure-requests",
  "speculation-rules": `"${SPECULATION_URL}"`,
});

const HTML_AUTHORITY = Object.freeze({
  schema_version: 1,
  route_count: 3,
  routes: [
    { request_path: "/", output_path: "index.html" },
    { request_path: "/about/", output_path: "about/index.html" },
    { request_path: "/404/", output_path: "404/index.html" },
  ],
  custom_404: { output_path: "404.html" },
});


function assertDirectHeaders(response) {
  for (const [name, value] of Object.entries(EXPECTED_DIRECT_HEADERS)) {
    assert.equal(response.headers.get(name), value, name);
  }
}


// The degraded fallback cannot safely compute a speculation-rules URL (that
// is one of the two things that may have just failed), so it omits that
// header entirely rather than guess. Everything else in the direct-header
// contract is a security header and still applies.
function assertSecurityHeaders(response) {
  for (const [name, value] of Object.entries(EXPECTED_DIRECT_HEADERS)) {
    if (name === "speculation-rules") {
      continue;
    }
    assert.equal(response.headers.get(name), value, name);
  }
}


function retained404(body = "authoritative error") {
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}


function retainedAuthority(authority = HTML_AUTHORITY) {
  return new Response(JSON.stringify(authority), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}


function retainedManifest(resource = {}) {
  return new Response(JSON.stringify({
    resources: [{
      logical_path: "speculation-rules.json",
      output_path: SPECULATION_URL.slice(1),
      request_url: SPECULATION_URL,
      sha256: SPECULATION_DIGEST,
      cache_class: "addressed",
      ...resource,
    }],
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}


function retainedAssets(options = {}) {
  return async (request) => {
    const path = new URL(request.url).pathname;
    if (path === "/release-html.json") {
      return retainedAuthority(options.authority);
    }
    if (path === "/404/") {
      return retained404(options.notFoundBody);
    }
    throw new Error(`unexpected ASSETS fetch: ${path}`);
  };
}


function context(response, options = {}) {
  const fallbackFetch = options.fetch ?? (async () => {
    throw new Error("unexpected ASSETS fetch");
  });
  return {
    request: new Request(options.url ?? "https://ardent.tools/missing", {
      method: options.method ?? "GET",
    }),
    next: async () => response,
    env: {
      ASSETS: {
        fetch: async (request) => {
          const path = new URL(request.url).pathname;
          if (path === "/release-resources.json") {
            return retainedManifest(options.speculationResource);
          }
          return fallbackFetch(request);
        },
      },
    },
  };
}


test("exact authority-derived aliases keep native 308 semantics and full headers", async () => {
  const cases = [
    ["/index.html", "/"],
    ["/about", "/about/"],
    ["/about/index.html", "/about/"],
    ["/404/index.html", "/404/"],
    ["/index.html?x=1", "/?x=1"],
    ["/about?x=1&x=2&encoded=%2F", "/about/?x=1&x=2&encoded=%2F"],
    [
      "/about/index.html?next=%2Fsystems%2F&flag=",
      "/about/?next=%2Fsystems%2F&flag=",
    ],
  ];
  for (const [source, target] of cases) {
    const response = new Response(null, {
      status: 308,
      headers: { Location: target },
    });
    const actual = await onRequest(context(response, {
      url: `https://ardent.tools${source}`,
      fetch: retainedAssets(),
    }));

    assert.notEqual(actual, response, source);
    assert.equal(actual.status, 308, source);
    assert.equal(actual.headers.get("Location"), target, source);
    assertDirectHeaders(actual);
  }
});


test("an arbitrary redirect becomes the retained 404", async () => {
  const response = new Response(null, {
    status: 301,
    headers: { Location: "/evidence/" },
  });
  const actual = await onRequest(context(response, {
    fetch: retainedAssets(),
  }));

  assert.equal(actual.status, 404);
  assertDirectHeaders(actual);
  assert.equal(await actual.text(), "authoritative error");
});


for (const [label, source, target] of [
  ["unowned", "/missing", "/missing/"],
  ["off-origin", "/about", "https://example.com/about/"],
  ["malformed", "/about", "http://[invalid"],
  ["query-dropping", "/about?x=1", "/about/"],
]) {
  test(`${label} 308 redirect becomes the retained 404`, async () => {
    const response = new Response(null, {
      status: 308,
      headers: { Location: target },
    });
    const actual = await onRequest(context(response, {
      url: `https://ardent.tools${source}`,
      fetch: retainedAssets(),
    }));

    assert.equal(actual.status, 404);
    assertDirectHeaders(actual);
    assert.equal(await actual.text(), "authoritative error");
  });
}


test("a generated 404 is replaced by the retained authority and full header contract", async () => {
  const response = new Response("edge-mutated error", {
    status: 404,
    headers: {
      "Cache-Control": "public, max-age=3600",
      "Content-Security-Policy": "default-src *",
    },
  });
  const actual = await onRequest(context(response, {
    fetch: async () => retained404(),
  }));

  assert.notEqual(actual, response);
  assert.equal(actual.status, 404);
  assert.equal(actual.statusText, "Not Found");
  assertDirectHeaders(actual);
  assert.equal(actual.headers.get("Content-Type"), "text/html; charset=utf-8");
  assert.equal(await actual.text(), "authoritative error");
});


test("a retained 410 preserves its body and receives the full header contract", async () => {
  const response = new Response("gone", {
    status: 410,
    statusText: "Gone",
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
  const actual = await onRequest(context(response));

  assert.notEqual(actual, response);
  assert.equal(actual.status, 410);
  assert.equal(actual.statusText, "Gone");
  assertDirectHeaders(actual);
  assert.equal(actual.headers.get("Content-Type"), "text/plain; charset=utf-8");
  assert.equal(await actual.text(), "gone");
});


for (const status of [200, 206, 204, 304]) {
  test(`unexpected status ${status} is replaced by retained 404 authority`, async () => {
    const stale = new Response([204, 304].includes(status) ? null : "stale asset", {
      status,
    });
    const fallback = retained404();
    let requested;
    const actual = await onRequest(context(stale, {
      fetch: async (request) => {
        requested = request;
        return fallback;
      },
    }));

    assert.equal(requested.url, "https://ardent.tools/404/");
    assert.equal(requested.method, "GET");
    assert.equal(actual.status, 404);
    assertDirectHeaders(actual);
    assert.equal(await actual.text(), "authoritative error");
  });
}


test("an unexpected custom-404 success would be guarded if routed", async () => {
  const response = retained404("platform custom 404");
  const actual = await onRequest(context(response, {
    url: "https://ardent.tools/404",
    fetch: retainedAssets({ notFoundBody: "authoritative error" }),
  }));

  assert.equal(actual.status, 404);
  assertDirectHeaders(actual);
  assert.equal(await actual.text(), "authoritative error");
});


test("HEAD errors preserve headers without returning a body", async () => {
  const response = new Response("authoritative error", {
    status: 404,
    headers: { "Cache-Control": "no-store" },
  });
  const actual = await onRequest(context(response, {
    method: "HEAD",
    fetch: async () => retained404(),
  }));

  assert.equal(actual.status, 404);
  assertDirectHeaders(actual);
  assert.equal(await actual.text(), "");
});


test("a status-mismatched retained 404 authority fails closed", async () => {
  // The ASSETS.fetch call itself succeeds here (it returns a Response); the
  // Response just carries the wrong status. That is a shape/integrity
  // mismatch in something that did come back, not a network-class failure,
  // so it must keep rejecting rather than degrade.
  const response = new Response("missing", { status: 404 });
  await assert.rejects(
    onRequest(context(response, {
      fetch: async () => new Response("failure", { status: 503 }),
    })),
    /retained 404 authority is unavailable/,
  );
});


test("an unreachable ASSETS binding degrades to a hardcoded 404", async () => {
  const response = new Response("missing", { status: 404 });
  const actual = await onRequest(context(response, {
    fetch: async () => {
      throw new TypeError("network connection lost");
    },
  }));

  assert.equal(actual.status, 404);
  assert.equal(actual.statusText, "Not Found");
  assertSecurityHeaders(actual);
  assert.equal(actual.headers.get("speculation-rules"), null);
  assert.equal(actual.headers.get("content-type"), "text/html; charset=utf-8");
  assert.match(await actual.text(), /404/);
});


test("an unreachable ASSETS binding degrades on HEAD requests too", async () => {
  const response = new Response("missing", { status: 404 });
  const actual = await onRequest(context(response, {
    method: "HEAD",
    fetch: async () => {
      throw new TypeError("network connection lost");
    },
  }));

  assert.equal(actual.status, 404);
  assertSecurityHeaders(actual);
  assert.equal(await actual.text(), "");
});


test("an unreachable manifest fetch also degrades to a hardcoded 404", async () => {
  const response = new Response("missing", { status: 404 });
  const actual = await onRequest({
    request: new Request("https://ardent.tools/missing"),
    next: async () => response,
    env: {
      ASSETS: {
        fetch: async (request) => {
          const path = new URL(request.url).pathname;
          if (path === "/release-resources.json") {
            throw new TypeError("network connection lost");
          }
          return retained404();
        },
      },
    },
  });

  assert.equal(actual.status, 404);
  assertSecurityHeaders(actual);
  assert.equal(actual.headers.get("speculation-rules"), null);
});


test("an invalid retained speculation identity fails closed", async () => {
  const response = new Response("missing", { status: 404 });
  await assert.rejects(
    onRequest(context(response, {
      fetch: async () => retained404(),
      speculationResource: { sha256: "2".repeat(64) },
    })),
    /retained speculation-rules identity is invalid/,
  );
});


test("non-tombstone server errors are not rewritten", async () => {
  const response = new Response("failure", {
    status: 503,
    headers: { "Cache-Control": "no-store" },
  });
  const actual = await onRequest(context(response));

  assert.equal(actual, response);
  assert.equal(actual.headers.get("Cache-Control"), "no-store");
});
