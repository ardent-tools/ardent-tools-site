// Cloudflare Pages does not apply `_headers` to Function responses. Keep this
// complete map synchronized with the artifact's validated `/*` contract, then
// apply it explicitly to every response generated here. `pages_runtime.py`
// fails closed if either authority drifts.

const DIRECT_RESPONSE_HEADERS = Object.freeze(
  /* DIRECT_RESPONSE_HEADERS_JSON_START */
  {
    "cache-control": "no-store, no-transform",
    "strict-transport-security": "max-age=31536000; includeSubDomains; preload",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "accelerometer=(), browsing-topics=(), camera=(), clipboard-read=(), clipboard-write=(), geolocation=(), gyroscope=(), hid=(), magnetometer=(), microphone=(), midi=(), payment=(), serial=(), usb=(), web-share=(), xr-spatial-tracking=()",
    "content-security-policy": "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self' 'wasm-unsafe-eval'; font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; manifest-src 'self'; worker-src 'none'; upgrade-insecure-requests"
  }
  /* DIRECT_RESPONSE_HEADERS_JSON_END */,
);

const GUARDED_ERROR_STATUSES = new Set([410]);
const AUTHORITATIVE_404_PATH = "/404/";
const HTML_AUTHORITY_PATH = "/release-html.json";
const RELEASE_MANIFEST_PATH = "/release-resources.json";
const ADDRESSED_SPECULATION_PATTERN = /^\/a\/([0-9a-f]{64})\.json$/;
const DEGRADED_NOT_FOUND_BODY =
  '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
  "<title>404</title></head><body><h1>404: no such path</h1>" +
  "<p>The retained error page is temporarily unavailable.</p>" +
  "</body></html>";

// Thrown only by fetchRetainedAsset() below, exclusively for a failure in the
// ASSETS.fetch call itself (network-class: the binding is unreachable, times
// out, or otherwise never returns a Response). Every other throw in this
// file — a non-200 status, invalid JSON, or a shape/identity mismatch on a
// Response that DID come back — stays a plain Error and stays fail-closed:
// that distinction is what lets authoritativeNotFound() degrade only for the
// former and still reject the latter.
class RetainedAssetUnavailableError extends Error {}

async function fetchRetainedAsset(context, request) {
  try {
    return await context.env.ASSETS.fetch(request);
  } catch (cause) {
    throw new RetainedAssetUnavailableError(
      `ASSETS.fetch is unavailable: ${cause instanceof Error ? cause.message : cause}`,
    );
  }
}

function degradedNotFound(requestMethod) {
  const guarded = new Response(
    requestMethod === "HEAD" ? null : DEGRADED_NOT_FOUND_BODY,
    { status: 404, statusText: "Not Found" },
  );
  guarded.headers.set("content-type", "text/html; charset=utf-8");
  for (const [name, value] of Object.entries(DIRECT_RESPONSE_HEADERS)) {
    guarded.headers.set(name, value);
  }
  return guarded;
}

function addAlias(aliases, source, target) {
  if (aliases.has(source)) {
    throw new Error(`retained HTML authority repeats alias ${source}`);
  }
  aliases.set(source, target);
}

function aliasTargets(authority) {
  if (
    authority === null ||
    typeof authority !== "object" ||
    authority.schema_version !== 1 ||
    !Number.isInteger(authority.route_count) ||
    !Array.isArray(authority.routes) ||
    authority.route_count !== authority.routes.length ||
    authority.custom_404 === null ||
    typeof authority.custom_404 !== "object"
  ) {
    throw new Error("retained HTML authority has an invalid shape");
  }

  const customOutput = authority.custom_404.output_path;
  if (
    typeof customOutput !== "string" ||
    !/^[A-Za-z0-9._~/-]+\.html$/.test(customOutput) ||
    customOutput.startsWith("/") ||
    customOutput.includes("//") ||
    customOutput.includes("%")
  ) {
    throw new Error("retained HTML authority has an invalid custom 404 path");
  }
  const customStem = `/${customOutput.slice(0, -".html".length)}`;
  const aliases = new Map();
  const canonicalPaths = new Set();

  for (const item of authority.routes) {
    if (
      item === null ||
      typeof item !== "object" ||
      typeof item.request_path !== "string" ||
      typeof item.output_path !== "string"
    ) {
      throw new Error("retained HTML authority has an invalid route");
    }
    const requestPath = item.request_path;
    canonicalPaths.add(requestPath);
    const expectedOutput = requestPath === "/"
      ? "index.html"
      : `${requestPath.slice(1)}index.html`;
    if (
      (requestPath !== "/" &&
        (!requestPath.startsWith("/") ||
          !requestPath.endsWith("/") ||
          requestPath.includes("//") ||
          requestPath.includes("%"))) ||
      item.output_path !== expectedOutput
    ) {
      throw new Error("retained HTML authority route/output mapping is invalid");
    }

    const physicalAlias = `/${item.output_path}`;
    if (physicalAlias !== requestPath) {
      addAlias(aliases, physicalAlias, requestPath);
    }
    const slashlessAlias = requestPath.slice(0, -1);
    // A top-level custom `404.html` shadows slash normalization at `/404`.
    // The repository owns that request through `_redirects`, so it is not an
    // authority-derived alias that may cross this Function.
    if (requestPath !== "/" && slashlessAlias !== customStem) {
      addAlias(aliases, slashlessAlias, requestPath);
    }
  }

  const customCanonical = `${customStem}/`;
  if (!canonicalPaths.has(customCanonical)) {
    throw new Error("retained HTML authority lacks the canonical custom 404 route");
  }
  return aliases;
}

async function retainedHtmlAuthority(context) {
  const authorityUrl = new URL(HTML_AUTHORITY_PATH, context.request.url);
  const response = await fetchRetainedAsset(
    context,
    new Request(authorityUrl, {
      method: "GET",
      headers: { Accept: "application/json" },
    }),
  );
  if (response.status !== 200) {
    throw new Error("retained HTML authority is unavailable");
  }
  try {
    return await response.json();
  } catch {
    throw new Error("retained HTML authority is invalid JSON");
  }
}

async function retainedSpeculationRulesUrl(context) {
  const manifestUrl = new URL(RELEASE_MANIFEST_PATH, context.request.url);
  const response = await fetchRetainedAsset(
    context,
    new Request(manifestUrl, {
      method: "GET",
      headers: { Accept: "application/json" },
    }),
  );
  if (response.status !== 200) {
    throw new Error("retained release manifest is unavailable");
  }
  let manifest;
  try {
    manifest = await response.json();
  } catch {
    throw new Error("retained release manifest is invalid JSON");
  }
  const matches = Array.isArray(manifest?.resources)
    ? manifest.resources.filter((item) =>
      item !== null &&
      typeof item === "object" &&
      item.logical_path === "speculation-rules.json"
    )
    : [];
  if (matches.length !== 1) {
    throw new Error("retained release manifest lacks one speculation-rules resource");
  }
  const item = matches[0];
  const match = typeof item.request_url === "string"
    ? item.request_url.match(ADDRESSED_SPECULATION_PATTERN)
    : null;
  if (
    item.cache_class !== "addressed" ||
    item.output_path !== item.request_url?.slice(1) ||
    typeof item.sha256 !== "string" ||
    match === null ||
    match[1] !== item.sha256
  ) {
    throw new Error("retained speculation-rules identity is invalid");
  }
  return item.request_url;
}

async function isOwnedHtmlAlias(context, response) {
  if (response.status !== 308) {
    return false;
  }
  const location = response.headers.get("Location");
  if (location === null) {
    return false;
  }

  const requestUrl = new URL(context.request.url);
  const authority = await retainedHtmlAuthority(context);
  const targetPath = aliasTargets(authority).get(requestUrl.pathname);
  if (targetPath === undefined) {
    return false;
  }
  try {
    const resolved = new URL(location, requestUrl);
    const expected = new URL(targetPath, requestUrl);
    expected.search = requestUrl.search;
    return resolved.href === expected.href;
  } catch {
    return false;
  }
}

function contractResponse(
  response,
  requestMethod,
  speculationRulesUrl,
  status = response.status,
) {
  const body = requestMethod === "HEAD" ? null : response.body;
  const guarded = new Response(body, {
    status,
    statusText: status === 404 ? "Not Found" : response.statusText,
    headers: response.headers,
  });
  for (const [name, value] of Object.entries(DIRECT_RESPONSE_HEADERS)) {
    guarded.headers.set(name, value);
  }
  guarded.headers.set("speculation-rules", `"${speculationRulesUrl}"`);
  return guarded;
}

async function authoritativeNotFound(context, speculationRulesUrl) {
  const fallbackUrl = new URL(AUTHORITATIVE_404_PATH, context.request.url);
  let resolvedSpeculationRulesUrl;
  let fallback;
  try {
    // The two ASSETS.fetch calls this needs have no data dependency on each
    // other, so run them concurrently rather than paying two sequential
    // round-trips on every visitor typo.
    [resolvedSpeculationRulesUrl, fallback] = await Promise.all([
      speculationRulesUrl,
      fetchRetainedAsset(
        context,
        new Request(fallbackUrl, {
          method: "GET",
          headers: { Accept: "text/html" },
        }),
      ),
    ]);
  } catch (error) {
    if (error instanceof RetainedAssetUnavailableError) {
      // The ASSETS binding itself is unreachable — not a shape/integrity
      // mismatch in something it did return — so degrade to a hardcoded 404
      // instead of letting the platform's raw unhandled-Error 500 through.
      return degradedNotFound(context.request.method);
    }
    throw error;
  }
  if (fallback.status !== 200) {
    throw new Error("retained 404 authority is unavailable");
  }
  return contractResponse(
    fallback,
    context.request.method,
    resolvedSpeculationRulesUrl,
    404,
  );
}

export async function onRequest(context) {
  const response = await context.next();

  // `_routes.json` excludes every retained page/resource and every owned
  // redirect. A success here can only be a removed asset resurrected from a
  // stale Pages cache, so replace it with the deployment-local 404 authority.
  if (
    (response.status >= 200 && response.status < 300) ||
    response.status === 304 ||
    response.status === 404
  ) {
    // Pass the pending promise, not its awaited value: authoritativeNotFound()
    // races it against its own ASSETS.fetch for the retained 404 body.
    return authoritativeNotFound(context, retainedSpeculationRulesUrl(context));
  }

  if (!GUARDED_ERROR_STATUSES.has(response.status)) {
    // Only exact aliases derived from the retained HTML authority may preserve
    // Pages' native redirect. An unowned or stale redirect is another missing
    // path and must not escape the authoritative error boundary.
    if (response.status >= 300 && response.status < 400) {
      const speculationRulesUrl = await retainedSpeculationRulesUrl(context);
      if (await isOwnedHtmlAlias(context, response)) {
        return contractResponse(
          response,
          context.request.method,
          speculationRulesUrl,
        );
      }
      return authoritativeNotFound(context, speculationRulesUrl);
    }
    return response;
  }

  // Asset-server responses have immutable headers in the Workers runtime.
  // Cloning preserves the 410 body and content metadata while applying the
  // complete repository-owned direct-response boundary above.
  const speculationRulesUrl = await retainedSpeculationRulesUrl(context);
  return contractResponse(
    response,
    context.request.method,
    speculationRulesUrl,
  );
}
