<!--
scope: ardent-tools-site project conventions
defers_to: none
tightens: content authoring rules for this repo may add site-specific constraints beyond typikon's own docs/AGENTIC.md
-->

# CLAUDE.md: ardent-tools

Consumer of typikon (`forkwright/typikon`, pinned by commit under `themes/typikon/`). The structural contract — templates, schemas, the CSP-enforcing gate — comes from typikon; this repo holds site-specific content, brand tokens, and the consumer-side template shadows the design needs.

## Standards

Authoring rules live in typikon's `docs/AGENTIC.md`. Read those before editing content here. Frontmatter must validate against the appropriate schema in `themes/typikon/schemas/` (page / section / journal-entry / faq). Run `themes/typikon/bin/typikon-validate .` to verify.

## Locked decisions

- **Theme**: `forkwright/typikon` via git submodule under `themes/typikon/`, pinned by commit (same SHA `ardent-site` pins as of this repo's scaffold — re-diff on refresh, don't assume the two stay in lockstep).
- **Strict CSP**: enforced via `_headers`. No inline scripts/styles anywhere. One carve-out: `script-src` carries `'wasm-unsafe-eval'` for the vendored asciinema-player's inline-compiled WASM core — see `_headers`' own comment for the verification status.
- **Self-hosted fonts and player**: fonts under `/fonts/`, the recording player under `/vendor/asciinema/`. No CDN of any kind.
- **No contact form, no newsletter**: `_headers`' `form-action` carries no third-party entry — unlike the sibling site's Buttondown allowlist, this site has no form at all.
- **Class-based syntax highlighting**: `config.toml [markdown.highlighting] style = "class"` (not the flat `highlight_code`/`highlight_theme` keys some design docs reference — those were Zola's pre-0.22 syntect config; Zola 0.22 moved to the Giallo highlighter under `[markdown.highlighting]`. See the comment in `config.toml` for the full note).
- **Deploy**: Cloudflare Pages via GitHub Actions on green `main` pushes. Cloudflare Pages project name: `ardent-tools`.

## Template shadow delta (the maintenance surface)

Everything under `templates/` here is either a full shadow of a typikon template (re-diff on every `typikon-refresh`) or new:

| File | Kind | Why |
|---|---|---|
| `templates/base.html` | Shadow | Adds `site.css`, `syntax.css`, the vendored player CSS/JS, and `site.js` after typikon's own stylesheet/scripts. Also layers Person JSON-LD onto the default Organization block. |
| `templates/index.html` | Shadow | Typikon's own `index.html` is the sibling site's hidden-nav home; this site's home keeps nav visible and has a fully different composition (DESIGN §4.1). |
| `templates/systems.html` | New | Data-driven systems index — loops `section.pages` through the catalog-row partial. |
| `templates/system.html` | New | `{% extends "page.html" %}`. Fact-row header + demo/diagram slot from `extra.*`, ahead of the markdown body. |
| `templates/demos.html` | New | `{% extends "page.html" %}`. Loops `extra.demos` / `extra.placards`. |
| `templates/consulting.html` | New | `{% extends "page.html" %}`. One data-driven block (`extra.engagement_shapes`) over otherwise-plain page content. |
| `templates/journal-entry.html` | Shadow | Drops the substrate's hardcoded `/lexicon/` link on the components line - sibling-site furniture this site does not have (upstream: typikon#27 thread). |
| `templates/partials/footer.html` | Shadow | Typikon's stock footer is one brand line + one flat link list; this site's footer needs three mono clusters + a sibling-brand line (DESIGN §3.7), which the flat list can't produce. |
| `templates/partials/ld-person.html` | New | Person JSON-LD, same pattern as typikon's six `ld-*.html` partials. |
| `templates/partials/term-panel.html` | New | The terminal-panel macro (real recording / honest placeholder / placard-without-panel) — the base primitive for every demo on the site. |
| `templates/partials/catalog-row.html` | New | The ledger-row macro `systems.html` and `index.html`'s selected-work block both call. |

`templates/partials/nav.html` is NOT shadowed — the Resume button is pure CSS (`.nav-links a:last-child`), and the Greek-hover mechanic in the stock partial stays dormant because no `greek`/`brand_greek` fields are ever set.

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
themes/typikon/bin/typikon-check .
```

Runs validate + zola check + zola build + csp-enforce locally; emits `skip` for lychee/pa11y/playwright unless those tools are on PATH (CI installs them; local dev gets the lite gate).

## Remotes

Not wired in this scaffold. The fleet convention (matching typikon and the sibling `ardent-site` repo) is `origin` = the forkwright forge, `github` = a push-mirror; wire both before the first real push, and run `kanon forge init ardent-tools/ardent-tools-site` to create the bare forge repo first (GitHub canonical: `github.com/ardent-tools/ardent-tools-site`).

## Open items from the build pass

- Three casts are launch-blocking per DESIGN.md §9 (thumos-boot, kanon-gate, aletheia-memory) and none are recorded yet — every demo on the site renders as an honest placeholder, not a fake, until a cast lands.
- The resume PDF (`resume/_build/kickertz_resume_2026_v3.pdf`) hasn't cleared operator review; `/resume/` links nothing yet, by design — no broken asset reference.
- `about.md`'s `## Influences` section is a structural placeholder, not five to eight invented entries — needs the operator's actual list.
- `logismos` and `harmonia` carry DESIGN-defined launch gates (CI + CLAUDE.md language for logismos; run instructions for harmonia) that are not yet cleared — see the build-pass report for current status of each.
