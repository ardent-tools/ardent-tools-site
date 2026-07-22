import { test } from '@playwright/test';

const targets = [
  ['home', '/'],
  ['systems', '/systems/'],
  ['system-aletheia', '/systems/aletheia/'],
  ['consulting', '/consulting/'],
  ['writing', '/writing/'],
  ['evidence', '/evidence/'],
];
const widths = [320, 375, 1440];

test.describe('review screenshots', () => {
  test.skip(!process.env.ARDENT_SCREENSHOTS, 'manual visual-review artifact capture');
  for (const width of widths) {
    for (const [name, route] of targets) {
      test(`${name} at ${width}`, async ({ page }) => {
        await page.setViewportSize({ width, height: width === 1440 ? 1000 : 900 });
        await page.goto(route, { waitUntil: 'networkidle' });
        await page.screenshot({
          path: `/tmp/ardent-evidence-screenshots/${width}-${name}.png`,
          fullPage: true,
        });
      });
    }
  }
});
