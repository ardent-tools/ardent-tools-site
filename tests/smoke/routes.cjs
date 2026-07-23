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
function deriveCastRoutes(systemsContentDir) {
  const dir = path.resolve(systemsContentDir);
  const routes = new Set();
  if (!fs.existsSync(dir)) return routes;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isFile() || !entry.name.endsWith('.md') || entry.name === '_index.md') continue;
    const lines = fs.readFileSync(path.join(dir, entry.name), 'utf8').split(/\r?\n/);
    const open = lines.indexOf('+++');
    const close = open === -1 ? -1 : lines.indexOf('+++', open + 1);
    if (close === -1) continue;
    const frontmatter = lines.slice(open + 1, close).join('\n');
    if (/^cast\s*=/m.test(frontmatter)) routes.add(`/systems/${entry.name.slice(0, -3)}/`);
  }
  return routes;
}

module.exports = { deriveRoutes, deriveCastRoutes };
