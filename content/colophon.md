+++
title = "Colophon"
description = "How this site is built: Zola and typikon, self-hosted fonts and player, the CSP posture, the gate it passes before every deploy, and what it deliberately doesn't do."
+++

# Colophon

Static site. Zola. Self-hosted fonts and player. No trackers, no analytics, no CDN.

This site is its own receipt: the repo is public, so the gate config, the CSP, and the recording scripts are all inspectable. [View source →](https://github.com/ardent-tools/ardent-tools-site)

<div class="receipt-table-wrap">

| What | Detail |
|---|---|
| Generator | [Zola](https://www.getzola.org/) 0.22.1, static-site build, no server-side runtime |
| Substrate | [typikon](https://github.com/forkwright/typikon), a shared Zola theme this site consumes as a git submodule and layers its own tokens and templates over |
| Fonts | Spectral and IBM Plex Mono, both self-hosted as WOFF2 under `/fonts/`, both OFL-licensed. No Google Fonts, no font CDN — the CSP's `font-src 'self'` blocks one even if referenced by mistake |
| Recording player | [asciinema-player](https://github.com/asciinema/asciinema-player) v3.17.0, vendored under `/vendor/asciinema/`, Apache-2.0 |
| Deploy | Cloudflare Pages, via GitHub Actions on green pushes to `main` |
| Tracking | None. No analytics, no cookies, no third-party requests of any kind |
| CSP — script-src | `'self'`, plus a `'wasm-unsafe-eval'` carve-out for the vendored player's inline-compiled WebAssembly core; in-browser QA against this exact policy is still open, see `_headers` |
| CSP — style-src | `'self'` only, no inline `style="..."` anywhere — code listings use Zola's class-based syntax highlighting instead of inline colors |
| CSP — form-action | `'self'` only. No third-party form destination, because the site carries no form at all |
| Family | Sibling of [Ardent Leatherworks](https://ardentleatherworks.com) — shared paper stock, shared press ink, shared flame mark |

</div>

## The gate

Every push runs the same sequence before anything deploys:

1. `typikon-validate` — frontmatter against JSON Schema
2. `zola check` — internal links and asset references
3. `zola build` — must be warning-free
4. `csp-enforce.sh` — greps the built HTML for anything the CSP above would block at runtime
5. `lychee` — external link integrity
6. `pa11y-ci` — WCAG 2.1 AA
7. Playwright — per-route smoke assertions

Only a fully green run deploys to Cloudflare Pages.

## What this site does not do

No trackers, no analytics, no cookies, no CDN-hosted anything, no contact form, no newsletter signup, no cadence promise on `/writing/`, no inflated maturity claim on any system page, and no fabricated demo recording — where a cast doesn't exist yet, the slot says so plainly instead of showing something that isn't real.
