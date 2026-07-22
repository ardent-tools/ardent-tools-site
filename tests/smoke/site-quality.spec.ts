import { test, expect } from '@playwright/test';

const path = require('node:path');
const { deriveRoutes } = require('./routes.cjs');
const outputDir = process.env.SITE_OUTPUT_DIR || 'public-local';
const routes: string[] = deriveRoutes(path.resolve(outputDir));
const viewports = [
  { width: 320, height: 900 },
  { width: 375, height: 900 },
  { width: 1440, height: 1000 },
];

for (const viewport of viewports) {
  for (const route of routes) {
    test(`${route} is structurally sound at ${viewport.width}px`, async ({ page }) => {
      const consoleErrors: string[] = [];
      const pageErrors: string[] = [];
      const requestErrors: string[] = [];
      const playerRequests: string[] = [];

      page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text());
      });
      page.on('pageerror', (error) => pageErrors.push(error.message));
      page.on('requestfailed', (request) => requestErrors.push(`${request.method()} ${request.url()}`));
      page.on('request', (request) => {
        if (request.url().includes('asciinema-player')) playerRequests.push(request.url());
      });

      await page.setViewportSize(viewport);
      const response = await page.goto(route, { waitUntil: 'networkidle' });
      expect(response?.status(), `${route} did not return 200`).toBe(200);

      const structure = await page.evaluate(() => {
        const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).map((node) => Number(node.tagName[1]));
        const headingSkips = headings.slice(1).filter((level, index) => level > headings[index] + 1);
        const ids = Array.from(document.querySelectorAll('[id]')).map((node) => node.id);
        const duplicateIds = ids.filter((id, index) => id && ids.indexOf(id) !== index);
        const unnamedLinks = Array.from(document.querySelectorAll('a')).filter((link) => {
          const imageAlt = Array.from(link.querySelectorAll('img')).map((img) => img.getAttribute('alt') || '').join(' ');
          return !(link.getAttribute('aria-label') || link.textContent || imageAlt).trim();
        }).length;
        const missingAlt = Array.from(document.querySelectorAll('img')).filter((img) => !img.hasAttribute('alt')).length;
        return {
          h1: document.querySelectorAll('h1').length,
          headingSkips,
          duplicateIds: [...new Set(duplicateIds)],
          unnamedLinks,
          missingAlt,
          overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          opacity: getComputedStyle(document.body).opacity,
          playerMarkup: document.querySelectorAll('[data-cast], link[href*="asciinema-player"], script[src*="asciinema-player"]').length,
        };
      });

      expect(structure.h1).toBe(1);
      expect(structure.headingSkips).toEqual([]);
      expect(structure.duplicateIds).toEqual([]);
      expect(structure.unnamedLinks).toBe(0);
      expect(structure.missingAlt).toBe(0);
      expect(structure.overflow, `${route} overflows by ${structure.overflow}px`).toBeLessThanOrEqual(0);
      expect(structure.opacity).toBe('1');
      expect(structure.playerMarkup).toBe(0);
      expect(playerRequests).toEqual([]);
      expect(consoleErrors).toEqual([]);
      expect(pageErrors).toEqual([]);
      expect(requestErrors).toEqual([]);

      if (viewport.width <= 375) {
        const utilitySizes = await page.locator('nav a, footer, .catalog-row-meta, .fact-row, .entry-date, .entry-components, .specs').evaluateAll((nodes) =>
          nodes
            .filter((node) => {
              const box = node.getBoundingClientRect();
              const style = getComputedStyle(node);
              return box.width > 0 && box.height > 0 && style.visibility !== 'hidden';
            })
            .map((node) => parseFloat(getComputedStyle(node).fontSize)),
        );
        expect(Math.min(...utilitySizes), `${route} has utility text below 12px`).toBeGreaterThanOrEqual(12);
      }
    });
  }
}

test('apostrophe title and Open Graph title decode exactly once', async ({ page }) => {
  await page.goto('/writing/coordination-that-isnt-voting/');
  const expected = "Coordination that isn't voting - Ardent Tools";
  await expect(page).toHaveTitle(expected);
  await expect(page.locator('meta[property="og:title"]')).toHaveAttribute('content', expected);
});

test('FAQ permalink names are non-empty and unique', async ({ page }) => {
  await page.goto('/faq/');
  const names = await page.locator('.faq-anchor').allTextContents();
  expect(names.every((name) => name.trim().length > 0)).toBe(true);
  expect(new Set(names).size).toBe(names.length);
});
