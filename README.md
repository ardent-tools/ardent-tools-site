# ardent.tools

Portfolio and consulting site for Ardent Tools - agent infrastructure engineering. Live at [ardent.tools](https://ardent.tools).

The thesis: evidence belongs beside the claim. System pages publish lifecycle boundaries, reproduction paths, source links, and dated measurement methods. A recording is rendered only when its real `.cast` artifact exists; planned recordings remain plain backlog entries.

## Substrate

Built on [typikon](https://github.com/forkwright/typikon), a shared Zola theme consumed here as a git submodule (`themes/typikon/`, pinned by commit - see `.gitmodules`). This repo holds only the site-specific content, brand tokens, and the small set of consumer-side template shadows the design needs beyond typikon's defaults (see `AGENTS.md` for the exact delta and why each override exists; `CLAUDE.md` is a one-line import stub pointing at it).

Agent-facing surfaces: [`/llms.txt`](https://ardent.tools/llms.txt) is the flat nav index for an agent fetching the live site; `AGENTS.md` is the equivalent for an agent cloning the repo.

## Build / run

Requires [Zola](https://www.getzola.org/) 0.22.1 and [Typst](https://typst.app/) 0.14.2 (both pinned in `.github/workflows/deploy.yml`), plus `pdftotext` and `pdffonts` for the repository-owned résumé check. The exact Nimbus Sans inputs, hashes, provenance, and license notices live under [`resume/fonts/`](resume/fonts/README.md); compilation ignores system and Typst-embedded fonts.

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

The default helper keeps every generated artifact in its `mktemp` directory,
removes that exact directory on exit or signal, and verifies that the worktree
and `playwright.config.ts` are unchanged. CI alone sets
`ARDENT_RETAIN_VALIDATED_PUBLIC=1`; that mode refuses to replace an existing
`public/` and moves the already validated production tree there for Wrangler.

The validated tree carries `build-revision.txt`; CI supplies the exact GitHub
revision. `release-html.json` records the full SHA-256 body of every retained
HTML route and the byte-identical custom 404, while marking the routes declared
canonical by `sitemap.xml`. `release-resources.json` covers the served non-HTML
regular resources in that exact tree, excluding the two Cloudflare Pages
control files and the resource manifest itself. The HTML authority is one of
those resources. Non-canonical resource URLs have one content digest and the
single release asset epoch from `config.toml`.

The post-deploy verifier refuses a different live sentinel or manifest, fetches
every retained HTML route, probes the custom 404, and requests every exact
resource URL without redirects. It compares full response-body digests and the
complete configured direct-response header boundary, including the derived
`Speculation-Rules` URL and the speculation-rules media type. The deploy job
revalidates the retained tree after installing Wrangler and immediately before
upload, so the uploaded directory is checked after the last dependency mutation.

The complete four-rule `_redirects` file is a strict local contract. The live
verifier requests a safe representative for every declaration without following
it; the two system wildcard probes are revision-specific, while the exact
`/demos` rule and its catch-all use their fixed non-destructive paths. It requires
the declared permanent status and exact same-origin destination. Redirect responses
are not assigned cache-header claims because Cloudflare Pages applies
`_redirects` before `_headers`.

## Deploy

GitHub Actions runs the full strict gate (schema validation, generator and résumé reproducibility, Zola check/build, revision, release-resource and cache contracts, CSP enforcement, link checks, strict XML/content checks, all-route WCAG AA, and Playwright browser assertions at desktop and narrow widths) on pushes to `main` and pull requests targeting `main`. Only a green push to `main` deploys the exact retained tree to Cloudflare Pages, then verifies that tree's sentinel, manifest, canonical pages, custom 404, tombstones, and resources at the live boundary. See `.github/workflows/deploy.yml`.

Cloudflare documents that a Pages deployment can leave an earlier asset in a
data center for up to one week and recommends a zone cache purge when stale
assets appear. The existing workflow secrets establish Pages deployment access,
not a zone ID and cache-purge permission, so this repository does not invent a
purge call. For the `v=2` transition release, the operator must purge the
`ardent.tools` zone after deployment and before accepting the live verifier.
Already-held browser cache entries cannot be revoked; the new epoch makes every
current non-canonical reference use a different key, while the release tombstone
keeps `/tapes/aletheia-memory.tape` absent through 2026-08-21. See
[Cloudflare Pages serving behavior](https://developers.cloudflare.com/pages/configuration/serving-pages/).

## License

Original site code: [PolyForm Shield 1.0.0](LICENSE), with an AI-training-prohibition addendum. Original content and copy: [CC BY-NC-ND 4.0](LICENSE-DOCS), same addendum. Third-party assets retain their own terms; the vendored résumé fonts and complete notices are documented under [`resume/fonts/`](resume/fonts/README.md).
