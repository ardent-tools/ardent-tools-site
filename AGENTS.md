<!--
scope: ardent-tools-site project conventions
defers_to: none
tightens: content authoring rules for this repo may add site-specific constraints beyond typikon's own docs/AGENTIC.md
-->

# AGENTS.md: ardent-tools

Consumer of typikon (`forkwright/typikon`, pinned by commit under `themes/typikon/`). The structural contract — templates, schemas, the CSP-enforcing gate — comes from typikon; this repo holds site-specific content, brand tokens, and the consumer-side template shadows the design needs.

## Standards

Authoring rules live in typikon's `docs/AGENTIC.md`. Read those before editing content here. Frontmatter must validate against the appropriate schema in `themes/typikon/schemas/` (page / section / journal-entry / faq). Run `themes/typikon/bin/typikon-validate .` to verify.

## Locked decisions

- **Theme**: `forkwright/typikon` via git submodule under `themes/typikon/`, pinned by commit (same SHA `ardent-site` pins as of this repo's scaffold — re-diff on refresh, don't assume the two stay in lockstep).
- **Strict CSP**: enforced via `_headers`. No inline scripts/styles anywhere. With zero published casts, `script-src` is `'self'` and carries no `wasm-unsafe-eval`; `bin/validate-site.py` fails if cast, player, and CSP state diverge.
- **Self-hosted application assets**: fonts live under `/fonts/`; the future recording player is vendored under `/vendor/asciinema/` and requested only when a real `cast` exists. Cloudflare Pages is the disclosed edge-delivery boundary.
- **No contact form, no newsletter**: `_headers`' `form-action` carries no third-party entry — unlike the sibling site's Buttondown allowlist, this site has no form at all.
- **Class-based syntax highlighting**: `config.toml [markdown.highlighting] style = "class"` (not the flat `highlight_code`/`highlight_theme` keys some design docs reference — those were Zola's pre-0.22 syntect config; Zola 0.22 moved to the Giallo highlighter under `[markdown.highlighting]`. See the comment in `config.toml` for the full note).
- **Deploy**: Cloudflare Pages via GitHub Actions on green `main` pushes. Cloudflare Pages project name: `ardent-tools`.

## Template shadow delta (the maintenance surface)

Everything under `templates/` here is either a full shadow of a typikon template (re-diff on every `typikon-refresh`) or new:

| File | Kind | Why |
|---|---|---|
| `templates/base.html` | Shadow | Adds `site.css`, `syntax.css`, conditional player blocks, and `site.js` after typikon's own stylesheet/scripts. Also resolves titles once, layers Person JSON-LD onto Organization, and adds the flame favicon set plus a light-only `theme-color`. |
| `templates/index.html` | Shadow | Evidence-lab home: consulting/role paths, a source-linked proof surface, selected systems, a derived fleet map, recent writing, and a consulting close. |
| `templates/page.html` | Shadow | Wraps `page.content` (+ product-gallery/video) in `.prose` (DESIGN-v1.1 §1.2) — the reading-measure cap for generic content pages (about, colophon, contact, resume, 404). Templates that override `{% block content %}` themselves (`system.html`, `faq.html`, `consulting.html`) do their own `.prose` wrap instead; this file's content block only renders for pages using `page.html` as-is. |
| `templates/faq.html` | Shadow | `.faq-page` article carries `.prose` too (DESIGN-v1.1 §1.2 — faq answers are an explicit prose context). Otherwise identical to typikon's own `faq.html`. |
| `templates/systems.html` | New | Data-driven full-fleet catalog: Systems loops `section.pages`; Libraries/Web/In-design loop the section ledger. Group counts are computed in-template. |
| `templates/system.html` | New | Fact-row header plus optional real-cast/diagram slot; player assets and panel require `extra.demo.cast`. Body prose narrows while evidence furniture stays at shell width. |
| `templates/evidence.html` | New | `/evidence/` register derived from the systems and writing sections. Current receipts and recording backlog are distinct; planned entries never render as players. |
| `templates/consulting.html` | New | `{% extends "page.html" %}`. h1+lede sit in a `<header class="consulting-header">` at the display tier (940px, DESIGN-v1.3 §1.3); the offer body is `.prose`-wrapped (680px@19, DESIGN-v1.1 §1.2 tier, DESIGN-v1.3 size); `extra.engagement_shapes` exits `.prose` entirely to a shell-width 3-col grid (`≥1024px`, DESIGN-v1.3 §1.3/§5). |
| `templates/journal-entry.html` | Shadow | Drops the substrate's hardcoded `/lexicon/` link on the components line - sibling-site furniture this site does not have (upstream: typikon#27 thread). Also wraps `page.content` in `.prose` (DESIGN-v1.3 §1.4) — the reading-measure cap every other content template already applies. |
| `templates/partials/nav.html` | Shadow | Current-page indicator (DESIGN-v1.1 §1.6 — `aria-current="page"` on the nav item whose URL prefixes `current_path`, home exact-match only) — typikon's stock partial has no path-comparison logic at all (filed upstream, typikon#25-adjacent, §9). |
| `templates/partials/footer.html` | Shadow | Typikon's stock footer is one brand line + one flat link list; this site's footer needs three mono clusters + a sibling-brand line (DESIGN §3.7), which the flat list can't produce. |
| `templates/partials/ld-person.html` | New | Person JSON-LD, same pattern as typikon's six `ld-*.html` partials. |
| `templates/partials/ld-organization.html` | Shadow | Preserves typikon's Organization JSON-LD while giving its logo the exact digest-plus-epoch resource identity required in raw JSON text. |
| `templates/partials/ld-article.html` | Shadow | Preserves typikon's Article JSON-LD while giving an optional image the exact raw-JSON resource identity. |
| `templates/partials/ld-product.html` | Shadow | Preserves typikon's Product JSON-LD while giving an optional image the exact raw-JSON resource identity. |
| `templates/partials/term-panel.html` | New | Terminal-player macro guarded by a real `demo.cast`; absent casts render nothing. |
| `templates/partials/asset-url.html` | New | Single non-canonical public-resource URL constructor: one Zola content digest plus the release-scoped `extra.asset_epoch`, with separate HTML-attribute and raw-JSON encodings. |
| `templates/partials/catalog-row.html` | New | The Tier-1 flagship ledger-row macro `systems.html` and `index.html`'s selected-work block both call. |
| `templates/partials/catalog-ledger.html` | New | Tier-2 (`grid()`, Libraries/Web) and Tier-3 (`register()`, In-design) ledger-row macros, both data-driven from `content/systems/_index.md`'s `[[extra.ledger]]` array — no hand-authored per-repo HTML. |
| `templates/atom.xml` | Shadow | Makes `/atom.xml` the canonical writing feed by deriving entries from the writing section. |
| `templates/sitemap.xml` | Shadow | Consumer mitigation for typikon#38: XML declaration at byte zero while preserving `skip_sitemap`. |

`templates/section.html` is NOT shadowed — every current `_index.md` in this repo sets an explicit `template =` (`systems.html`, `journal-section.html`) or is the root home (`index.html`); nothing renders through typikon's generic `section.html` today, so there is nothing for a `.prose` wrap to affect. Add the shadow if a future section index needs one.

**No `partials/assert.html` import anywhere.** The pinned typikon commit predates that macro (added later in typikon's history); templates here that extend typikon's `page.html`/`section.html`/etc. still work fine without it — those theme templates skip the extra required-field assertions at this pin. Importing it from a consumer template would break the build outright (the file doesn't exist at this pin). Check this again before bumping the submodule.

## Refreshing the typikon theme

```
cd themes/typikon && git fetch origin && git checkout <new-sha> && cd ../..
git add themes/typikon
git commit -m "chore: bump typikon to <sha>"
```

Re-diff every shadowed template (see table above) against the new commit before committing — a shadow that silently drifts from the theme's own evolution is the accepted maintenance cost of this override path (typikon's `consumer_css`/per-page CSS hook is documented but not actually wired; see `docs/AGENTIC.md` in the submodule).

## Local gate

```
bin/check-site.sh
```

Runs the CI-equivalent gate against isolated production and local-base-url
outputs and fails closed when required tools are missing. It preserves tracked
consumer configuration, including `playwright.config.ts`; the pinned Typikon
runner does not, and its owning defect is tracked upstream as typikon#39.
Normal runs remove their exact `mktemp` output and preserve worktree state. CI
sets `ARDENT_RETAIN_VALIDATED_PUBLIC=1` to move the already validated production
tree into an initially absent, ignored `public/` directory for deployment. CI
also passes `ARDENT_BUILD_REVISION` so that tree carries the exact commit in
`build-revision.txt`; the live verifier requires the same revision after deploy.
It retains `release-html.json`, which covers every HTML route (including routes
excluded from the sitemap) plus the byte-identical custom 404 with full SHA-256
bodies. `release-resources.json` covers served non-HTML regular resources except
`_headers`, `_redirects`, and the resource manifest itself; the HTML authority
is included as a resource. Non-canonical resource references carry a content
digest plus the central `extra.asset_epoch`. The verifier fetches every retained
HTML route, separately requests a revision-specific missing route, checks every
manifest resource, and requires the complete configured direct-response header
map plus the special speculation-rules media type. `_redirects` responses are
checked only for status and location because Cloudflare Pages resolves redirects
before `_headers`; the complete four-rule file is validated locally, and
production probes a revision-specific representative for every declaration
without following it.
The résumé compiles twice with only the pinned, licensed inputs under
`resume/fonts/`; system and Typst-embedded fonts are disabled, and `pdffonts`
must report only embedded/subsetted Nimbus Sans Regular and Bold.

## Remotes

`origin` points directly at `github.com/ardent-tools/ardent-tools-site` — no forge remote, no push-mirror. This diverges from the fleet convention (typikon and the sibling `ardent-site` repo run `origin` = the forkwright forge, `github` = a push-mirror); a forge remote can be added later via `kanon forge init ardent-tools/ardent-tools-site` if this repo joins that convention, but nothing here depends on it today.

## Open items from the build pass

- No casts are published. The evidence register shows recording targets as backlog prose; no player request, panel, WATCH link, or WebAssembly CSP exception exists until a real cast lands and the contract gate is updated.
- The resume PDF is live: `content/resume.md` links `/files/cody-kickertz-resume.pdf`, the file is present under `static/files/`, and it builds through.
- `about.md` carries no `## Influences` section (removed in v1.1 phase A pending the operator's actual 5-8 entries; add it back only with real content).
- `logismos` and `harmonia` carry DESIGN-defined launch gates (CI + CLAUDE.md language for logismos; run instructions for harmonia) that are not yet cleared. No build-pass report exists in this repo; check `kanon planning` for each repo's current gate status.
