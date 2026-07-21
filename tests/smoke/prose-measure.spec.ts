// prose-measure.spec.ts — DESIGN-v1.3 §1.5 verification gate.
//
// The fontTools numbers behind the 680px@19px prose tier (§1.2) are
// static analysis against Spectral's measured glyph widths, not a live
// render. This closes the loop in an actual browser: at a representative
// desktop viewport, .prose paragraphs on a long-form page should average
// 70-85 real characters per rendered line (the guideline band §1 cites).
//
// Runs against every *.spec.ts under tests/smoke/ per
// themes/typikon/ci/playwright.config.ts (static server on :8080).

import { test, expect } from '@playwright/test';

const ROUTES = ['/writing/three-ways-to-count/', '/about/'];
const VIEWPORT = { width: 1440, height: 1000 };
const MIN_CHARS_PER_LINE = 70;
const MAX_CHARS_PER_LINE = 85;
// Paragraphs shorter than this rarely wrap to more than a line or two at
// 680px and would skew the average toward noise rather than measure.
const MIN_SAMPLE_CHARS = 200;

for (const route of ROUTES) {
  test(`${route} .prose averages ${MIN_CHARS_PER_LINE}-${MAX_CHARS_PER_LINE} real chars/line at ${VIEWPORT.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(VIEWPORT);
    await page.goto(route);

    const paragraphs = page.locator('.prose > p');
    const count = await paragraphs.count();
    expect(count, `${route} has no .prose > p paragraphs to measure`).toBeGreaterThan(0);

    let totalChars = 0;
    let totalLines = 0;

    for (let i = 0; i < count; i++) {
      const p = paragraphs.nth(i);
      const text = (await p.innerText()).trim();
      if (text.length < MIN_SAMPLE_CHARS) continue;

      const metrics = await p.evaluate((el) => {
        const style = window.getComputedStyle(el);
        let lineHeight = parseFloat(style.lineHeight);
        if (Number.isNaN(lineHeight)) {
          // 'normal' resolves to no fixed px value in getComputedStyle;
          // approximate at the browser-default 1.2x font-size.
          lineHeight = parseFloat(style.fontSize) * 1.2;
        }
        return { height: el.getBoundingClientRect().height, lineHeight };
      });

      const lines = Math.max(1, Math.round(metrics.height / metrics.lineHeight));
      totalChars += text.length;
      totalLines += lines;
    }

    expect(totalLines, `${route}'s sampled .prose paragraphs rendered no measurable lines`).toBeGreaterThan(0);

    const avgCharsPerLine = totalChars / totalLines;
    expect(avgCharsPerLine).toBeGreaterThanOrEqual(MIN_CHARS_PER_LINE);
    expect(avgCharsPerLine).toBeLessThanOrEqual(MAX_CHARS_PER_LINE);
  });
}
