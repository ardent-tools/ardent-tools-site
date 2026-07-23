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
| Generator | [Zola](https://www.getzola.org/) 0.22.1, static-site build, no server-side runtime |
| Substrate | [typikon](https://github.com/forkwright/typikon), a shared Zola theme this site consumes as a git submodule and layers its own tokens and templates over |
| Fonts | Spectral and IBM Plex Mono, both self-hosted as WOFF2 under `/fonts/`, both OFL-licensed. No Google Fonts, no font CDN — the CSP's `font-src 'self'` blocks one even if referenced by mistake |
| Recording contract | [asciinema-player](https://github.com/asciinema/asciinema-player) v3.17.0 is vendored for future casts, but no player CSS or JavaScript is requested unless a system has a real `cast` artifact |
| Deploy | Cloudflare Pages, via GitHub Actions on green pushes to `main` |
| Delivery boundary | Authored output makes no remote third-party runtime/application requests. Cloudflare Pages provides edge delivery and may add platform reporting or protection unless the operator disables it |
| CSP — script-src | `'self'` only. With zero published casts, no player is requested and no `wasm-unsafe-eval` exception remains |
| CSP — style-src | `'self'` only, no inline `style="..."` anywhere — code listings use Zola's class-based syntax highlighting instead of inline colors |
| CSP — form-action | `'self'` only. No third-party form destination, because the site carries no form at all |
| Family | Sibling of [Ardent Leatherworks](https://ardentleatherworks.com) — shared paper stock, shared press ink, shared flame mark |

</div>

## The gate

Pushes to `main` and pull requests targeting `main` run the same sequence before anything deploys:

1. `typikon-validate` — frontmatter against JSON Schema
2. `zola check` — internal links and asset references
3. `zola build` — must complete successfully
4. `csp-enforce.sh` — the pinned Typikon syntactic preflight for inline script/style and disallowed remote asset forms
5. `lychee` — external link integrity
6. `pa11y-ci` — WCAG 2.1 AA
7. Strict XML/content audit — feed completeness, sitemap resolution, structured-data URLs, artifact revision, cache-rule overlap, conditional player assets, recording-plan safety, and claim contracts
8. pa11y and Playwright — every generated public HTML route at the required browser widths

## What this site does not do

The authored site has no analytics, cookies, contact form, newsletter signup, remote font or script dependency, cadence promise on `/writing/`, inflated maturity label, or fabricated terminal output. Cloudflare Pages remains the delivery boundary. With no casts published, recording plans appear only as plans and the built site requests no player assets.
