<!--
scope: ardent-tools-site project conventions
defers_to: none
tightens: content authoring rules for this repo may add site-specific constraints beyond typikon's own docs/AGENTIC.md
-->

# AGENTS.md: ardent-tools

Consumer of typikon (`forkwright/typikon`, pinned by commit under `themes/typikon/`). The structural contract — templates, schemas, the CSP-enforcing gate — comes from typikon; this repo holds site-specific content, brand tokens, and the consumer-side template shadows the design needs.

## Standards

Authoring rules live in typikon's `docs/AGENTIC.md`. Read those before editing content here. Frontmatter must validate against the appropriate schema — typikon's own built-ins in `themes/typikon/schemas/` (page / section / journal-entry / faq) for content using one of typikon's shipped templates, or this repo's own `schemas/registry.toml` + `schemas/*.schema.json` for the six custom templates (home, about, consulting, evidence, systems index, system dossier) — see `themes/typikon/docs/SCHEMAS.md#consumer-schema-registry` for the registration contract. Run `themes/typikon/bin/typikon-validate .` to verify either way; a custom template with no registry entry fails closed rather than silently inheriting page's shape.

Voice binds all site copy — content pages, captions, microcopy, the consulting page. The contract is [docs/VOICE.md](docs/VOICE.md).

## Locked decisions

- **Theme**: `forkwright/typikon` via git submodule under `themes/typikon/`, pinned by commit (same SHA `ardent-site` pins as of this repo's scaffold — re-diff on refresh, don't assume the two stay in lockstep).
- **Strict CSP**: enforced via `_headers` and mirrored in `bin/header_contract.py` and the error-boundary Function. No inline scripts/styles anywhere. Individual system pages (template `system.html`) that publish a cast need the vendored WebAssembly player, so `script-src` carries `'wasm-unsafe-eval'` under `/systems/*/` only — every other path, including the systems catalog itself (`/systems/`, template `systems.html`, which lists casts but never renders the player), keeps plain `'self'`. `bin/validate-site.py` fails if cast, player, and CSP state diverge (drop every cast and the exception must drop with it).
- **Self-hosted application assets**: fonts live under `/fonts/`; the recording player is vendored under `/vendor/asciinema/` and requested only on a page whose system has a real `cast`. Cloudflare Pages is the disclosed edge-delivery boundary.
- **No contact form, no newsletter**: `_headers`' `form-action` carries no third-party entry — unlike the sibling site's Buttondown allowlist, this site has no form at all.
- **Class-based syntax highlighting**: `config.toml [markdown.highlighting] style = "class"` (not the flat `highlight_code`/`highlight_theme` keys some design docs reference — those were Zola's pre-0.22 syntect config; Zola 0.22 moved to the Giallo highlighter under `[markdown.highlighting]`. See the comment in `config.toml` for the full note).
- **Deploy**: Cloudflare Pages via GitHub Actions on green `main` pushes. Cloudflare Pages project name: `ardent-tools`.

## Template shadow delta (the maintenance surface)

Everything under `templates/` here is either a full shadow of a typikon template (re-diff on every `typikon-refresh`) or new:

| File | Kind | Why |
|---|---|---|
| `templates/base.html` | Shadow | Adds `css/skins/leather.css` (typikon's own first-party skin, split out of core in typikon#55 — see the file's header comment for why this repo now links it explicitly rather than leaving it to core's stylesheet), `site.css`, `syntax.css`, conditional player blocks, and `site.js` after typikon's own stylesheet/scripts. Also resolves titles once, layers Person JSON-LD onto Organization, and adds the flame favicon set plus a light-only `theme-color`. |
| `templates/index.html` | Shadow | Evidence-lab home: consulting/role paths, a source-linked proof surface, selected systems, a derived fleet map, recent writing, and a consulting close. |
| `templates/page.html` | Shadow | Renders a designed `.page-header` (title + description) ahead of `page.content`, then wraps content and gallery/video furniture in `.prose`. It keeps digest-addressed Open Graph images, layers structured data through `super()`, and retains the product-purchase omission. The shared no-H1 assertion guards the Markdown body. Templates that override `{% block content %}` themselves (`system.html`, `faq.html`, `consulting.html`) do their own header + `.prose` wrap instead. |
| `templates/faq.html` | Shadow | `.faq-page` article carries `.prose` too — faq answers are an explicit prose context. Answers render through the `markdown(inline=true)` filter (not plain-escaped text) so a path or case-study mention in `extra.questions[].a` becomes a real link; `partials/ld-faq.html` is shadowed to match (see below). Structured data layers through `super()`, and the shared no-H1 assertion guards its intro. |
| `templates/systems.html` | New | Data-driven full-fleet catalog: Systems loops `section.pages`; Libraries/Web/In-design loop the section ledger. Group counts are computed in-template. |
| `templates/system.html` | New | Fact-row header plus optional real-cast/diagram slot; player assets and panel require `extra.demo.cast`. Body prose narrows while evidence furniture stays at shell width. |
| `templates/evidence.html` | New | `/evidence/` register derived from the systems and writing sections. Current receipts and recording backlog are distinct; planned entries never render as players. Both registers (current evidence, published casts) are real `<table>` markup — the content is tabular, so `<thead>`/`<th scope="col">`/`<td>` carry that structure for assistive tech instead of an `aria-hidden` header row over an unlabeled `<a>`-wrapped list. |
| `templates/consulting.html` | New | `{% extends "page.html" %}`. h1+lede sit in a `<header class="consulting-header">` at the display tier (940px); the offer body is `.prose`-wrapped (680px@19); `extra.engagement_shapes` exits `.prose` entirely to a shell-width 3-col grid (`≥1024px`). |
| `templates/journal-entry.html` | Shadow | Keeps site-specific structured-data layering, progress/reveal/figure/end furniture, the `.prose` wrapper, navigation arrow spans, and the shared no-H1 assertion. The theme has dropped its old hardcoded `/lexicon/` link, so that former delta is closed. |
| `templates/journal-section.html` | Shadow | Groups `section.pages` by `extra.tier` (Notes first, then Research) instead of typikon's one flat date-sorted list, reusing the systems-catalog group grammar (`.catalog-group` / `.group-index` / `.group-caption` / `.catalog-index`) and the theme's own `.journal-list` row markup. Every entry must carry `extra.tier`; `bin/site.py` fails closed if one is missing. |
| `templates/partials/nav.html` | Shadow | Current-page indicator — `aria-current="page"` on the nav item whose URL prefixes `current_path`, home exact-match only — typikon's stock partial has no path-comparison logic at all (filed upstream, typikon#25-adjacent). |
| `templates/partials/footer.html` | Shadow | Typikon's stock footer is one brand line + one flat link list; this site's footer needs three mono clusters + a sibling-brand line, which the flat list can't produce. |
| `templates/partials/ld-person.html` | New | Person JSON-LD, following Typikon's Schema.org-emitting `ld-*` partial pattern. |
| `templates/partials/ld-organization.html` | Shadow | Gives the logo its full-digest raw-JSON resource identity, emits the confirmed legal entity as `legalName`, and keeps Typikon's required-field assertion. |
| `templates/partials/ld-article.html` | Shadow | Gives an optional image its full-digest raw-JSON resource identity and keeps Typikon's required-field assertions. |
| `templates/partials/ld-product.html` | Shadow | Gives an optional image its full-digest raw-JSON resource identity, gates checkout structured data on sourced purchasable state, and keeps Typikon's required-field assertions. |
| `templates/partials/ld-faq.html` | Shadow | Renders each `extra.questions[].a` through the same `markdown(inline=true)` pass `faq.html` uses, then `striptags`, before JSON-encoding; it keeps Typikon's required-field assertions. |
| `templates/partials/term-panel.html` | New | Terminal-player Tera 2 component guarded by a real `demo.cast`; absent casts render nothing. |
| `templates/partials/asset-url.html` | New | Single logical public-resource URL constructor; `bin/content_address.py` rewrites its output to a full-SHA-256 physical path after dependencies are finalized. Separate HTML-attribute and raw-JSON call sites remain explicit. |
| `templates/partials/catalog-row.html` | New | The Tier-1 flagship ledger-row Tera 2 component `systems.html`'s flagship zone calls; home's own selected-work block renders through `partials/feature-block.html` instead. |
| `templates/partials/catalog-ledger.html` | New | Tier-2 (`grid`, Libraries/Web) and Tier-3 (`register`, In-design) ledger-row components, both data-driven from `content/systems/_index.md`'s `[[extra.ledger]]` array — no hand-authored per-repo HTML. |

`templates/section.html` is NOT shadowed — every current `_index.md` in this repo sets an explicit `template =` (`systems.html`, `journal-section.html`) or is the root home (`index.html`); nothing renders through typikon's generic `section.html` today, so there is nothing for a `.prose` wrap to affect. Add the shadow if a future section index needs one.

The Tera 2 assertions are globally namespaced components, so consumer shadows call them directly without import aliases. Provenance fields remain conditional: `extra.words_source` accompanies an `extra.words` override, while product price fields govern `extra.price_source`; neither belongs on every page. The root Atom feed is no longer shadowed: `config.extra.feed_source_section = "writing/_index.md"` delegates scoped membership and freshness to Typikon.

### Template-review checklist

- No `.plate` treatment (`.spec-plate`, `.proof-record`, `.term-mat`, `.engagement-shape`, ...) on non-evidence content — plates are reserved for evidence artifacts, never prose or navigation (§1.3).
- No two consecutive feature-block grid mirrorings (`.feature-lead` directly followed by another `.feature-lead`, or `.feature-mirror` by another `.feature-mirror`) without a deliberate break in the sequence.
- At most one element per rendered page carries a given `view-transition-name` (the `.vtn-*` classes) — check every page a system's row/title/h1 could appear on together before adding a new call site.

## Refreshing the typikon theme

```
cd themes/typikon && git fetch origin && git checkout <new-sha> && cd ../..
git add themes/typikon
git commit -m "chore: bump typikon to <sha>"
```

Re-diff every shadowed template (see table above) against the new commit before committing — a shadow that silently drifts from the theme's own evolution is the accepted maintenance cost of this override path. typikon#55 (landed in the 4f8c1531 -> b61228cb refresh) made the `consumer_css`/`{% block styles %}`/`head_extra`/`nav`/`footer`/`ld_json`/`scripts`/`content` extension surface real — it is wired now, not merely documented — which is exactly what will let several of the shadows in the table above collapse to a smaller block override, or delete outright, in a dedicated follow-up. This refresh deliberately did not start that migration (see `docs/AGENTIC.md` in the submodule for the surface itself, and each shadow's own table row above for its current disposition).

## Local gate

```
python3 bin/site.py gate
```

Runs the repository-owned strict gate against isolated production and
local-base-url outputs and fails closed when required tools are missing. It preserves tracked
consumer configuration, including `playwright.config.ts`; the pinned Typikon
runner does not, and its owning defect is tracked upstream as typikon#39.
Normal runs remove their exact `mktemp` output and preserve worktree state. CI
sets `ARDENT_RETAIN_VALIDATED_PUBLIC=1` to move the already validated production
tree into an initially absent, ignored `public/` directory for deployment. CI
also passes `ARDENT_BUILD_REVISION` so that tree carries the exact commit in
`build-revision.txt`; the live verifier requires the same revision after deploy.
All local `serve`, `build`, and `check` commands also go through
`python3 bin/site.py`; do not invoke Zola directly. That entrypoint verifies the
tracked catalog and career-claim receipt before Zola runs, while `serve` watches
their complete source sets and atomically re-derives them after changes. A
refresh that cannot reach a stable input snapshot stops and reaps the authoring
server; it must never continue with stale generated bytes.
It retains `release-html.json`, which covers every HTML route (including routes
excluded from the sitemap) plus the byte-identical custom 404 with full SHA-256
bodies. `release-resources.json` covers served non-HTML regular resources except
`_headers`, `_redirects`, `_routes.json`, and the resource manifest itself; the
HTML authority and `runtime-boundary.json` are included as resources, with the
latter binding the Function source, derived route table, and production
`wrangler.toml`. Non-canonical resources are emitted only at
`/a/<full-sha256>.<extension>` paths whose digest matches the final served bytes;
logical source aliases and query cache-busters are forbidden. Rewriting is
schema-aware for HTML, CSS, JSON-LD, Web App Manifest, and speculation-rule
list-source fields, and covers supported inline and reference-style Markdown
destinations. Addressed JavaScript is limited to enumerated paths and reviewed
full-body digests, while dependency-capable addressed XML fails closed.
`asset-retention.json` plus `retained-assets/` preserve prior physical
bytes and special media types. A changed current map must be recorded with
`python3 bin/site.py retain-assets`. Pull-request and push CI select the event's
base/before revision; recovery dispatch validates `HEAD^`. Its ledger must remain
an exact append-only prefix of the trusted base's ledger, or extend it via one
checkpoint entry that hash-chains over everything it replaces
(`python3 bin/asset_retention.py compact`) — history grows one entry per
asset-touching commit with no hard ceiling; a soft warning at 128 entries
names the compaction command well before the deep, corruption-only safety
limit. See the module docstring in `bin/asset_retention.py` for the full
design.
The verifier fetches every retained
HTML route, separately requests a revision-specific missing route, checks every
manifest resource, and requires the complete configured direct-response header
map plus every current or historical speculation-rules media type. The Pages
route table intentionally leaves `/a/*` on native static serving; the manifest
proves every known member, while unknown physical-namespace misses retain native
Pages behavior. `_redirects` responses are
checked only for status and location because Cloudflare Pages resolves redirects
before `_headers`; the complete rule file (SUPPORTED_REDIRECTS in `bin/redirect_contract.py`) is validated locally, and
production probes a safe representative for every declaration without following
it. The two system wildcard probes are revision-specific; the exact `/demos`
rule and its catch-all use fixed non-destructive paths, and `/404` plus
`/404.html` canonicalize directly to `/404/`.
The résumé compiles twice with only the pinned, licensed inputs under
`resume/fonts/`; system and Typst-embedded fonts are disabled, and `pdffonts`
must report only embedded/subsetted Nimbus Sans Regular and Bold.

## Remotes

Do not infer push authority from fleet intent or copied prose. Run `git remote -v` before every push, and treat any URL resolving to GitHub as a direct GitHub write. This repository's GitHub owner is `ardent-tools`, not `forkwright`; changing its forge topology crosses an organization boundary and requires an explicit authority decision. Use `kanon forge list` to derive which repositories the forge actually knows.

## Open items from the build pass

- Published casts live at `static/casts/<name>.cast` with a reproduction recipe at `static/tapes/<name>.driver.sh` (asciinema, not VHS - VHS cannot emit `.cast`); for each, the player, panel, WATCH link, recipe link, and the shared `wasm-unsafe-eval` CSP exception are live and gate-enforced by `validate-site.py`. Systems without a cast show their recording targets as backlog prose, and their planned `.tape` VHS storyboards under `static/tapes/` stand until their casts land.
- The résumé PDF source is `static/files/cody-kickertz-resume.pdf`, linked from `/hire/` (its home page — `/resume/` 301s there) and `/about/`; the home hero links to `/hire/` rather than triggering the download directly. Finalization emits a physical full-digest URL with the stable download filename `cody-kickertz-resume.pdf`.
- `about.md` carries no `## Influences` section (removed in v1.1 phase A pending the operator's actual 5-8 entries; add it back only with real content).
- `logismos` and `harmonia` carry DESIGN-defined launch gates (CI + CLAUDE.md language for logismos; run instructions for harmonia) that are not yet cleared. No build-pass report exists in this repo; check `kanon planning` for each repo's current gate status.
- **Un-shadowing pass pending, now that typikon#55's consumer design API is real.** `base.html`'s remaining reasons to be a full shadow (the explicit stylesheet list, the favicon override, the Person JSON-LD layering) map onto the theme's own `{% block styles %}`/`config.extra.consumer_css`/`{% block head_extra %}`/`{% block ld_json %}` slots closely enough to be worth re-evaluating as a smaller block override rather than a full-file copy. `journal-entry.html` still carries several site-specific deltas: super-layered structured data, progress/reveal/figure/end furniture, the `.prose` wrapper, navigation arrow spans, and the adopted assertion component. Treat it as its own comparison rather than a single-block shrink. `partials/footer.html` and `partials/nav.html` could potentially shrink to `{% block footer %}`/`{% block nav %}` overrides once/if the theme's own default markup converges further with this site's structural needs — their current deltas are real markup/logic, not drift, so this is a shrink candidate, not a deletion one. Deliberately not started in the 4f8c1531 -> b61228cb refresh (typikon v0.4.2-2) — mixing theme-drift reconciliation with un-shadowing in one diff makes both unreviewable; do them as a separate PR, per shadow, against what typikon's API actually supports today.
