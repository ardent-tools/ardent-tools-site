# ardent.tools

Portfolio and consulting site for Ardent Tools - agent infrastructure engineering. Live at [ardent.tools](https://ardent.tools).

The thesis: the demo is the page, prose is the caption. Every system page leads with a recording or a diagram, states what the recording proves and what it doesn't, and every number on the site carries a measurement method next to it.

## Substrate

Built on [typikon](https://github.com/forkwright/typikon), a shared Zola theme consumed here as a git submodule (`themes/typikon/`, pinned by commit - see `.gitmodules`). This repo holds only the site-specific content, brand tokens, and the small set of consumer-side template shadows the design needs beyond typikon's defaults (see `AGENTS.md` for the exact delta and why each override exists; `CLAUDE.md` is a one-line import stub pointing at it).

Agent-facing surfaces: [`/llms.txt`](https://ardent.tools/llms.txt) is the flat nav index for an agent fetching the live site; `AGENTS.md` is the equivalent for an agent cloning the repo.

## Build / run

Requires [Zola](https://www.getzola.org/) 0.22.1 (pinned; see `.github/workflows/deploy.yml`).

`themes/typikon/` ships as a git submodule - a plain clone leaves it empty and `zola build` fails outright. Initialize it first:

```bash
git submodule update --init --recursive
```

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

GitHub Actions runs the full strict gate (validate, zola check/build, CSP enforcement, link check, WCAG AA, and a Playwright line-length check against two representative pages - `tests/smoke/prose-measure.spec.ts`) on every push and pull request, and deploys to Cloudflare Pages on green pushes to `main`. See `.github/workflows/deploy.yml`.

## License

Code: [PolyForm Shield 1.0.0](LICENSE), with an AI-training-prohibition addendum. Content and copy: [CC BY-NC-ND 4.0](LICENSE-DOCS), same addendum.
