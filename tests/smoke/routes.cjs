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

module.exports = { deriveRoutes };
