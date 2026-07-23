+++
title = "kanon"
description = "A private standards and dispatch control plane: lint and gate tooling, code intelligence, and PR/issue orchestration with public configuration receipts."
weight = 3
template = "system.html"

[extra]
badge = "PRIVATE · CASE STUDY"
private = true
stack = "Rust · MCP server · standards-as-code"

[extra.headline_claim]
claim = "Six featured public system repos carry Kanon configuration; enforcement remains repository-specific"
receipt = ".kanon-ci.toml in aletheia, thumos, harmonia, akroasis, logismos, and hamma"

[extra.demo]
system = "kanon"
action = "lint --fix, then gate"
target = "run against the public aletheia repo, not kanon's own source"
cast = "/casts/kanon-gate.cast"
recipe = "/tapes/kanon-gate.driver.sh"
duration = "54s"
cols = 80
rows = 24
poster = "npt:0:52"
shows = "The standards engine finding and fixing a seeded, explicitly labeled violation class, then running the configured gate against a public repository."
not_shows = "kanon's own source - the engine ran against a public clone."
fallback = [
  "$ kanon lint $PROOF_FILE; rc=$?; test $rc -eq 1 && ok VIOLATION_OK",
  "/tmp/aletheia-cast/scripts/release-feature-policy.toml:54 [TOML/missing-trailing-comma] multi-line array element missing trailing comma",
  "KANON_VIOLATION_OK",
  "$ kanon lint --fix $PROOF_FILE && ok FIX_OK",
  "Applied 1 fix(es) across 1 file(s):",
  "KANON_FIX_OK",
  "$ kanon lint $PROOF_FILE && ok LINT_CLEAN_OK",
  "KANON_LINT_CLEAN_OK",
  "$ kanon gate . && ok GATE_OK",
  "  ok  light gate passed — push to the forge for authoritative clippy + nextest + verifier",
  "KANON_GATE_OK",
]
transcript = '''
$ # kanon - lint and gate against a pinned public clone of aletheia
$ git rev-parse --short=12 HEAD
05b699215dd4
$ git status --porcelain | wc -l
0
$ # SEEDED VIOLATION - missing TOML trailing comma - absent from the pinned source
$ seed $PROOF_FILE
$ kanon lint $PROOF_FILE; rc=$?; test $rc -eq 1 && ok VIOLATION_OK
/tmp/aletheia-cast/scripts/release-feature-policy.toml:54 [TOML/missing-trailing-comma] multi-line array element missing trailing comma
KANON_VIOLATION_OK
$ kanon lint --fix $PROOF_FILE && ok FIX_OK
Applied 1 fix(es) across 1 file(s):
  1 fix(es) in /tmp/aletheia-cast/scripts/release-feature-policy.toml

KANON_FIX_OK
$ git diff -- $PROOF_FILE
@@ -49,3 +49,7 @@ name = "full-headless"
 crate = "aletheia"
 features = ["recall", "storage-fjall", "embed-candle", "cc-provider", "tls"]
 reason = "Full headless deployment: recall plus ML plus Claude Code provider and TLS, no TUI."
+
+kanon_recording_proof = [
+  "seed",
+]
$ kanon lint $PROOF_FILE && ok LINT_CLEAN_OK
KANON_LINT_CLEAN_OK
$ kanon gate . && ok GATE_OK
[kanon gate (light: fmt + check + advisory parity + deterministic-derive check + lint)]  /tmp/aletheia-cast

── config check
  skip  not a kanon workspace

── cargo fmt

── cargo check
    Finished `dev` profile [optimized + debuginfo] target(s) in 1.29s

── advisory ignore parity
  ok  advisory ignore lists are in parity and no review-by dates are due

── derive check (deterministic)
  skip  not a kanon workspace

── fleet-names freshness
  skip  fleet-names freshness check skipped: fleet discovery root is missing or incomplete (partial checkout). Embedded registry is authoritative.

  PASS  config check
  PASS  cargo fmt
  PASS  cargo check
  PASS  advisory ignore parity
  PASS  derive check (deterministic)
  PASS  fleet-names freshness

  ok  light gate passed — push to the forge for authoritative clippy + nextest + verifier
KANON_GATE_OK
$ # not shown: kanon's own source - the engine ran against a public clone
'''
+++

## What it is

Every repository in this fleet answers to the same control plane. kanon carries it - a lint engine, a CI-exact gate system, a code-intelligence layer, and a PR/issue-orchestration MCP server. Its source is private. The public receipt is narrower and directly inspectable - the six featured public system repositories carry `.kanon-ci.toml`, while each repository chooses its own enforcement scope. Presence of configuration is not a claim that every repository runs the same checks or blocks on the same rules.

Concretely, `kanon lint` finds mechanical rule violations across a repo (`--fix` auto-resolves the fixable class; diff-aware use supplies both `--diff-base <base>` and `--diff-head <head>`, or one `--rev-range <base>..<head>`), and `kanon gate` runs the fast-feedback check (format, compile check, lint), with a `--full` mode that adds clippy, the full test suite, and a Gate-Passed commit trailer once everything's clean.

## Decisions and trade-offs

### Private by choice, not by necessity

kanon stays private not because the source is sensitive, but because it isn't yet hardened for public traffic the way the fleet's other repos are. Systems built in employment are a different case entirely - employer property, described on this site only as experience. A public repo with real stars and real issues would be the stronger portfolio artifact - just not yet, not until the tool is ready for that audience.

| Decision | Chose | Rejected | Cost accepted |
|---|---|---|---|
| Rule enforcement | One shared rule registry with repository-owned configuration and differing enforcement scopes | One unqualified claim that every repository is gated identically | Coupling remains explicit; a rule change can affect repos that opt into that scope |
| Recording target | Run `kanon lint` / `kanon gate` against the public aletheia repo | Recording against kanon's own source | A seeded violation, if used, is labeled on-screen as seeded |

## What's solid / what's open

**Solid:** `kanon lint` and `kanon lint --fix` for mechanical rule violations, `kanon gate` and `kanon gate --full` for fast-feedback and full-verification paths, an MCP server surface for PR/issue orchestration and code intelligence, and repository-owned `.kanon-ci.toml` configuration in the six featured public system repositories.

**Open:** not yet hardened for public traffic, which is the entire reason it stays private. No public issue tracker or contribution path exists while that's true.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Reproduction method | Where to check |
|---|---|---|
| 319,025 Rust code lines; 371,075 physical Rust lines | `tokei -o json . | jq '.Rust | {code, comments, blanks, physical: (.code + .comments + .blanks)}'` at private `main` `d5eab9fac35c`, 2026-07-22 | private source; dated artifact available on request |
| 12 Cargo workspace members | `cargo metadata --no-deps --format-version 1 | jq '.workspace_members | length'` at `d5eab9fac35c` | private source; dated artifact available on request |
| 6,877 test-attribute occurrences | `rg -o '#\[(tokio::)?test' --glob '*.rs' | wc -l` at the same commit, 2026-07-22 | private source; dated artifact available on request |
| Binary version 0.1.12 | binary metadata and `--help` output at the same snapshot | private source; dated artifact available on request |

</div>

## Where to look

- Repo: private (case-study page only; no public link)
- Evidence available here: the public configuration matrix below, the system receipt above, and a redacted review pack on request

| Public system | Configuration receipt | Enforcement claim |
|---|---|---|
| [thumos](/systems/thumos/) | [`.kanon-ci.toml`](https://github.com/forkwright/thumos/blob/main/.kanon-ci.toml) | Declared by that repository's configuration |
| [aletheia](/systems/aletheia/) | [`.kanon-ci.toml`](https://github.com/forkwright/aletheia/blob/main/.kanon-ci.toml) | Declared by that repository's configuration |
| [harmonia](/systems/harmonia/) | [`.kanon-ci.toml`](https://github.com/forkwright/harmonia/blob/main/.kanon-ci.toml) | Declared by that repository's configuration |
| [akroasis](/systems/akroasis/) | [`.kanon-ci.toml`](https://github.com/forkwright/akroasis/blob/main/.kanon-ci.toml) | Declared by that repository's configuration |
| [logismos](/systems/logismos/) | [`.kanon-ci.toml`](https://github.com/forkwright/logismos/blob/main/.kanon-ci.toml) | Declared by that repository's configuration |
| [hamma](/systems/hamma/) | [`.kanon-ci.toml`](https://github.com/forkwright/hamma/blob/main/.kanon-ci.toml) | Declared by that repository's configuration |
