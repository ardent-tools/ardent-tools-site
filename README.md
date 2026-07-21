# ardent.tools

Portfolio and consulting site for Ardent Tools - agent infrastructure engineering. Live at [ardent.tools](https://ardent.tools).

The thesis: the demo is the page, prose is the caption. Every system page leads with a recording or a diagram, states what the recording proves and what it doesn't, and every number on the site carries a measurement method next to it.

## Substrate

Built on [typikon](https://github.com/forkwright/typikon), a shared Zola theme consumed here as a git submodule (`themes/typikon/`, pinned by commit - see `.gitmodules`). This repo holds only the site-specific content, brand tokens, and the small set of consumer-side template shadows the design needs beyond typikon's defaults (see `CLAUDE.md` for the exact delta and why each override exists).

## Build / run

Requires [Zola](https://www.getzola.org/) 0.22.1 (pinned; see `.github/workflows/deploy.yml`).

```bash
zola serve      # local dev server with live reload
zola build      # build to public/
zola check      # internal links + asset references
```

Frontmatter validation and the full local gate:

```bash
themes/typikon/bin/typikon-validate .   # frontmatter against JSON Schema
themes/typikon/bin/typikon-check .      # validate + zola check + zola build + csp-enforce
                                         # (+ lychee/pa11y/playwright when those tools are on PATH)
```

## Deploy

GitHub Actions runs the full strict gate (validate, zola check/build, CSP enforcement, link check, WCAG AA, Playwright smoke) on every push and pull request, and deploys to Cloudflare Pages on green pushes to `main`. See `.github/workflows/deploy.yml`.

## License

Code: [PolyForm Shield 1.0.0](LICENSE), with an AI-training-prohibition addendum. Content and copy: [CC BY-NC-ND 4.0](LICENSE-DOCS), same addendum.
