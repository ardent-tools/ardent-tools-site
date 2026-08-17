const fs = require('node:fs');
const path = require('node:path');

function deriveRoutes(outputDir) {
  const root = path.resolve(outputDir);
  const routes = [];

  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const absolute = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(absolute);
      } else if (entry.isFile() && entry.name.endsWith('.html')) {
        const relative = path.relative(root, absolute).split(path.sep).join('/');
        if (relative === '404.html' && fs.existsSync(path.join(root, '404/index.html'))) continue;
        if (relative === 'index.html') routes.push('/');
        else if (relative.endsWith('/index.html')) routes.push(`/${relative.slice(0, -10)}`);
        else routes.push(`/${relative}`);
      }
    }
  }

  walk(root);
  return [...new Set(routes)].sort();
}

// The set of system routes whose frontmatter publishes a cast. Derived from the
// source `[extra.demo] cast = ...` declaration, not the built markup, so the
// structural test verifies the built page reflects the declaration (and no other
// page carries a stray player panel) rather than asserting a tautology.
//
// staticDir is optional so the schema-level unit tests (player-asset-audit.node.mjs)
// can exercise frontmatter parsing without a real static/ tree. When given, it
// enforces the site's own rule (bin/validate-site.py: a declared cast must point
// at a file that exists) as a hard failure rather than silently trusting the
// declaration - the same fail-closed posture resolvePlayerAssetUrls uses for a
// missing manifest pair, so a dangling `cast = ` can never be read as "no cast".
function deriveCastRoutes(systemsContentDir, staticDir) {
  const dir = path.resolve(systemsContentDir);
  const routes = new Set();
  if (!fs.existsSync(dir)) return routes;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isFile() || !entry.name.endsWith('.md') || entry.name === '_index.md') continue;
    const sourcePath = path.join(dir, entry.name);
    const lines = fs.readFileSync(sourcePath, 'utf8').split(/\r?\n/);
    const open = lines.indexOf('+++');
    const close = open === -1 ? -1 : lines.indexOf('+++', open + 1);
    if (close === -1) continue;
    const frontmatter = lines.slice(open + 1, close).join('\n');
    const match = frontmatter.match(/^cast\s*=\s*"([^"]+)"/m);
    if (!match) continue;
    if (staticDir) {
      const castFile = path.join(path.resolve(staticDir), match[1].replace(/^\//, ''));
      if (!fs.existsSync(castFile) || !fs.statSync(castFile).isFile()) {
        throw new Error(`${sourcePath}: cast points to missing ${castFile}`);
      }
    }
    routes.add(`/systems/${entry.name.slice(0, -3)}/`);
  }
  return routes;
}

// Zola/content_address finalizes the vendored player CSS/JS into content-addressed
// `/a/<sha256>.<ext>` URLs (see bin/content_address.py ADDRESS_PREFIX); no served
// URL contains the literal string "asciinema-player" once a build is finalized.
// The exact physical pair is a resources manifest's own record of what those
// logical resources became, so it is the only correct match target for both
// markup selectors and intercepted network requests.
//
// NOTE: takes the manifest file directly rather than an output directory.
// release-resources.json (bin/release_manifest.py) is production-only - it
// hardcodes the canonical https:// origin - so it never exists beside the
// loopback-base-url build check-site.sh's browser gate actually serves.
// That build's own local-asset-map.json (bin/content_address.py's --map
// output, same {resources:[{logical_path,request_url}]} shape) is the
// correct source there; the caller selects which manifest matches the
// output tree under test.
function resolvePlayerAssetUrls(manifestPath) {
  manifestPath = path.resolve(manifestPath);
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const resourceUrls = new Map();
  for (const item of manifest.resources || []) {
    if (item && typeof item.logical_path === 'string' && typeof item.request_url === 'string') {
      resourceUrls.set(`/${item.logical_path}`, item.request_url);
    }
  }
  const cssUrl = resourceUrls.get('/vendor/asciinema/asciinema-player.css');
  const jsUrl = resourceUrls.get('/vendor/asciinema/asciinema-player.min.js');
  if (!cssUrl || !jsUrl) {
    throw new Error(`${manifestPath} does not resolve the asciinema player asset pair`);
  }
  return { cssUrl, jsUrl };
}

// Pure per-route verdict: a cast route must show the exact player asset pair
// exactly once, in markup and in network requests; every other route must show
// neither, in either signal. Kept independent of Playwright so the leak and
// omission directions are unit-testable without a browser (player-asset-audit.node.mjs).
function auditPlayerAssetPresence({
  route,
  isCastRoute,
  cssMarkupCount,
  jsMarkupCount,
  cssRequestCount,
  jsRequestCount,
}) {
  const expected = isCastRoute ? 1 : 0;
  const signals = [
    ['player CSS markup', cssMarkupCount],
    ['player JS markup', jsMarkupCount],
    ['player CSS request', cssRequestCount],
    ['player JS request', jsRequestCount],
  ];
  return signals
    .filter(([, count]) => count !== expected)
    .map(([label, count]) => `${route}: expected ${expected} ${label}, found ${count}`);
}

module.exports = { deriveRoutes, deriveCastRoutes, resolvePlayerAssetUrls, auditPlayerAssetPresence };
