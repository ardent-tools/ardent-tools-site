+++
title = "Colophon"
description = "How this site is built: Zola and typikon, self-hosted assets, strict CSP, evidence checks, and Cloudflare Pages delivery."
+++

# Colophon

Static Zola site. Self-hosted application assets. No site-authored analytics or cookies, and no remote third-party runtime/application requests in authored output.

The repo is public: the gate config, CSP, source content, recording plans, and derived-data checks are inspectable. [View source →](https://github.com/ardent-tools/ardent-tools-site)

<div class="receipt-table-wrap">

| What | Detail |
|---|---|
| Generator | [Zola](https://www.getzola.org/) 0.22.1, static application with no dynamic backend; one bounded Pages Function enforces the error boundary |
| Substrate | [typikon](https://github.com/forkwright/typikon), a shared Zola theme this site consumes as a git submodule and layers its own tokens and templates over |
| Fonts | Spectral and IBM Plex Mono, both self-hosted from repository WOFF2 sources and served at physical full-digest paths, both OFL-licensed. No Google Fonts, no font CDN — the CSP's `font-src 'self'` blocks one even if referenced by mistake |
| Résumé fonts | Nimbus Sans Regular and Bold are pinned with their hashes and AGPL-with-font-exception notices under `resume/fonts/`; Typst compiles with system and embedded fonts disabled, twice, and the gate byte-compares both PDFs |
| Career claims | A closed typed authority gives selected repeated Marine Corps facts required IDs and value/unit/display bindings, records the operator-authorized truth-release basis, and sets a one-year review window. The receipt says the underlying service record was not inspected by this audit; the gate checks exact About, Typst, and shipped-PDF renderings and rejects residual claim-domain values outside them |
| Recording contract | [asciinema-player](https://github.com/asciinema/asciinema-player) v3.17.0 is vendored for future casts, but no player CSS or JavaScript is requested unless a system has a real `cast` artifact |
| Deploy | Cloudflare Pages, via GitHub Actions on green pushes to `main` |
| Delivery boundary | Authored output makes no remote third-party runtime/application requests. Cloudflare Pages provides edge delivery and may add platform reporting or protection unless the operator disables it |
| Release identity | Non-redirect HTML and logical-path responses are configured `no-store, no-transform`; every non-HTML resource lives at a full-SHA-256 physical path (`/a/<digest>.<ext>`) and is provably immutable by construction, so it is instead configured `public, max-age=31536000, immutable`. Production probes the complete direct-response header contract for both. Cloudflare Pages evaluates `_redirects` before `_headers`, so redirects are instead checked for exact permanent status and same-origin destination. Non-canonical resources exist only at full-SHA-256 physical paths whose names match their final served bytes; no logical alias or query cache-buster is deployed. Rewriting follows the owned HTML, CSS, JSON-LD, Web App Manifest, header, redirect, and supported inline/reference-style Markdown URL fields; canonical Atom/Sitemap XML rejects asset dependencies, and JavaScript is pinned by path plus complete body digest. The hash-chained retention ledger keeps prior physical bytes and media-type rules, grows without a hard entry cap, and compacts into one checkpoint entry on request rather than ever being edited or truncated. Pull-request and push CI select the event base/before revision, while recovery dispatch validates `HEAD^`; the selected ledger must remain an exact append-only prefix of that base, or extend it through one such checkpoint. The artifact also enforces Pages' 25 MiB per-file and 100-header-rule bounds. One retained authority — `/release-html.json` — hashes every HTML route and the custom 404; another — `/release-resources.json` — covers served non-HTML resources except the Pages control files and its own manifest. Both are served and requestable |
| CSP — script-src | `'self'` only. With zero published casts, no player is requested and no `wasm-unsafe-eval` exception remains |
| CSP — style-src | `'self'` only, no inline `style="..."` anywhere — code listings use Zola's class-based syntax highlighting instead of inline colors |
| CSP — form-action | `'self'` only. No third-party form destination, because the site carries no form at all |
| Construction | AI agents build and maintain this site - the templates, the stylesheet, the prose, the release machinery - under my direction, through the gate below. The gate covers what's automatable; I check the rest by hand |
| Method | The [essays](/writing/) carry the operating method behind this site and the systems it documents — how the gates, counts, and review loops actually run |
| Family | Sibling of [Ardent Leatherworks](https://ardentleatherworks.com) — shared paper stock, shared press ink, shared flame mark |

</div>

## The gate

Pushes to `main` and pull requests targeting `main` run the same sequence before anything deploys:

1. `typikon-validate` — frontmatter against JSON Schema
2. Retention authority — require the trusted base revision's ledger as an exact append-only prefix (or a hash-chained checkpoint of it), then verify every retained filename, byte digest, media type, and bound
3. `bin/site.py check` — reject derivation drift, then run Zola's internal-link and asset check
4. Python and Node regressions — release, runtime, cache, evidence, and error-boundary contracts
5. Résumé authority — compile twice from pinned fonts, byte-compare the PDFs, inspect embedded fonts, validate extracted text, and check the career manifest
6. `bin/site.py build` — build the production tree; derive its HTML, runtime, and resource authorities; run the pinned CSP preflight and strict XML/content/header/claim audit
7. `lychee` — external link integrity against that production tree
8. Local-origin build and browser gate — serve a second build, then run all-route WCAG 2.1 AA and Playwright checks at every configured width
9. Cleanliness check — prove the gate did not alter tracked or untracked worktree state; production subsequently verifies every retained route, the custom 404, and every manifest resource at the live boundary

## What this site does not do

The authored site has no analytics, cookies, contact form, newsletter signup, remote font or script dependency, cadence promise on `/writing/`, inflated maturity label, or fabricated terminal output. Cloudflare Pages remains the delivery boundary. With no casts published, recording plans appear only as plans and the built site requests no player assets.
