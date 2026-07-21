+++
title = "kanon"
description = "The standards engine that gates every other repo on this site: a lint/gate CLI, code intelligence, and PR/issue orchestration, private by choice."
weight = 3
template = "system.html"

[extra]
badge = "PRIVATE · CASE STUDY"
private = true
stack = "Rust · MCP server · standards-as-code"
demo_len = "0:75"

[extra.headline_claim]
claim = "Gates every other public repo on this site"
receipt = "aletheia, thumos, hamma, harmonia, and logismos each carry a standards/ pointer into kanon's canonical rule set"

[extra.demo]
system = "kanon"
action = "lint --fix, then gate"
target = "run against the public aletheia repo, not kanon's own source"
duration = "0:75"
placeholder = "RECORDING FORTHCOMING: kanon lint finds a violation (seeded for the recording, labeled on-screen as SEEDED VIOLATION — LABELED IN-CAST) → kanon lint --fix clears the mechanical class → kanon gate runs clean"
shows = "The standards engine finding and fixing a real violation class, then passing a clean gate — against a public repo, so nothing of kanon's own source is exposed."
not_shows = "kanon's own source. This is a private repo by choice, not because the tool doesn't work — the case-study framing exists precisely so the design is visible without the code."
+++

## What it is

kanon is the standards and dispatch control plane the rest of this fleet is built and gated against: a lint engine, a CI-exact gate system, a code-intelligence layer, and a PR/issue-orchestration MCP server. It's private, but not because it doesn't work — every other public repo on this site (aletheia, thumos, hamma, harmonia, logismos) points its own `standards/` directory at kanon's canonical rule set and runs kanon's gate before anything merges. This page is a case study rather than a source tour: the design thinking is visible without exposing the tool itself.

Concretely, `kanon lint` finds mechanical rule violations across a repo (`--fix` auto-resolves the fixable class, `--diff-base` scopes it to a PR's actual diff), and `kanon gate` runs the fast-feedback check — format, compile check, lint — with a `--full` mode that adds clippy, the full test suite, and a Gate-Passed commit trailer once everything's clean.

## Decisions and trade-offs

### One standards engine, not five copy-pasted lint configs

Every repo in the fleet could have carried its own clippy config, its own commit-message convention, its own ad hoc CI script. Instead they all point at one shared rule registry that kanon enforces identically everywhere. The cost is coupling: a rule change in kanon can, in principle, break a gate in a repo that hasn't been touched in months. The alternative — five repos slowly drifting toward five different conventions — was judged worse, because "consistent standards across a fleet of independent systems" is the actual thesis kanon exists to prove.

### Private by choice, not by necessity

kanon stays private not because the source is sensitive, but because it isn't yet hardened for public traffic the way the fleet's other repos are. That's a different reason than ergon-tools' or nosologia's privacy (those are employer property, not a choice). The trade-off accepted here: a stronger portfolio artifact would be a public repo with real stars and real issues; the current call prioritizes not shipping a standards tool to strangers before it's ready for that audience.

### Demo against a public repo, never kanon's own source

The recording plan for this page runs `kanon lint` / `kanon gate` against the public aletheia repo rather than kanon itself. This proves the engine actually does something — finds a violation, fixes it, gates clean — without exposing a single line of kanon's private source. A seeded violation, if one is used to make the recording deterministic, is labeled on-screen as seeded; the alternative (silently staging a fake finding) would undercut the whole site's "no fabricated demos" rule.

## What's solid / what's open

**Solid:** `kanon lint` and `kanon lint --fix` for mechanical rule violations, `kanon gate` and `kanon gate --full` for the fast-feedback and full-verification paths, an MCP server surface for PR/issue orchestration and code intelligence, and a standards registry that five other repos in this fleet already depend on in production.

**Open:** not yet hardened for public traffic, which is the entire reason it stays private for now. No public issue tracker or contribution path exists while that's true.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Method | Where to check |
|---|---|---|
| 311,090 lines Rust (code-only), 361,727 including comments | `tokei` against a local clone, 2026-07-20 | private repo; artifact available on request |
| 13 workspace crates | crate count in the workspace `Cargo.toml` | private repo; artifact available on request |
| ~6,628 test-attribute occurrences | `rg -c '#\[(tokio::)?test'`, 2026-07-20 | private repo; artifact available on request |
| Binary version 0.1.12 | `kanon lint --help` / `kanon gate --help` output, captured 2026-07-20 | private repo; artifact available on request |

</div>

## Where to look

- Repo: private (case-study page only; no public link)
- What it's like to use: see the recording above once it lands, or ask for a redacted review pack
- The five public repos it gates: [thumos](/systems/thumos/), [aletheia](/systems/aletheia/), [harmonia](/systems/harmonia/), [logismos](/systems/logismos/), [hamma](/systems/hamma/)
