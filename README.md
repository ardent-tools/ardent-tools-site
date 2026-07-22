# ardent.tools

Portfolio and consulting site for Ardent Tools - agent infrastructure engineering. Live at [ardent.tools](https://ardent.tools).

The thesis: evidence belongs beside the claim. System pages publish lifecycle boundaries, reproduction paths, source links, and dated measurement methods. A recording is rendered only when its real `.cast` artifact exists; planned recordings remain plain backlog entries.

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
bin/check-site.sh                       # isolated CI-equivalent strict gate;
                                        # fails closed if required tools are absent
```

## Deploy

GitHub Actions runs the full strict gate (schema validation, generator cleanliness, Zola check/build, CSP enforcement, link checks, strict XML/content checks, all-route WCAG AA, and Playwright browser assertions at desktop and narrow widths) on pushes to `main` and pull requests targeting `main`. Only a green push to `main` deploys to Cloudflare Pages. See `.github/workflows/deploy.yml`.

## License

Code: [PolyForm Shield 1.0.0](LICENSE), with an AI-training-prohibition addendum. Content and copy: [CC BY-NC-ND 4.0](LICENSE-DOCS), same addendum.
