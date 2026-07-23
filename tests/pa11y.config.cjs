const path = require('node:path');
const { deriveRoutes } = require('./smoke/routes.cjs');

const outputDir = process.env.SITE_OUTPUT_DIR || 'public-local';
const baseURL = process.env.TYPIKON_BASE_URL || 'http://127.0.0.1:8080';
const urls = deriveRoutes(path.resolve(outputDir)).map((route) => new URL(route, baseURL).href);

module.exports = {
  defaults: {
    standard: 'WCAG2AA',
    timeout: 30000,
    wait: 200,
    chromeLaunchConfig: { args: ['--no-sandbox', '--disable-dev-shm-usage'] },
    ignore: ['WCAG2AA.Principle1.Guideline1_3.1_3_1.H49.AlignAttr'],
    hideElements: '',
  },
  urls,
};
