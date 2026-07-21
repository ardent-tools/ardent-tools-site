+++
title = "aletheia"
description = "Self-hosted AI agents with persistent memory. One binary, no containers, no external databases — a knowledge graph that carries forward across sessions."
weight = 2
template = "system.html"

[extra]
badge = "TUI DEFAULT · DESKTOP IN PREVIEW"
repo = "https://github.com/forkwright/aletheia"
stack = "Rust · single binary · Datalog-backed memory"
demo_len = "1:30"

[extra.headline_claim]
claim = "One binary — no containers, no external databases, no sidecars"
receipt = "aletheia/README.md, Architecture section"

[extra.demo]
system = "aletheia"
action = "memory recall across turns"
target = "local model, no cloud key"
duration = "1:30"
placeholder = "RECORDING FORTHCOMING: TUI session — state a fact in turn 1, ask something unrelated in turn 2, ask for recall in turn 3, agent cites the turn-1 fact back correctly"
shows = "A fact stated in turn 1, recalled correctly and cited back in turn 3, running against a local model with no cloud API key."
not_shows = "The desktop app — it's a v1.0-target preview, installed separately from source, not the default onboarding path this recording uses."
+++

## What it is

aletheia is a self-hosted runtime for AI agents that remember. Talk to an agent, and it carries the conversation forward: what you told it last week, the preferences you stated once, a knowledge graph it builds from every session rather than starting cold each time. Each agent gets its own character, goals, and memory, and agents can coordinate with each other rather than existing as isolated chat sessions.

It ships as a single binary — no containers, no external database, no sidecar processes. The only outbound network dependency at runtime is whichever LLM provider you configure; on first run it downloads embedding-model files from Hugging Face, then runs fully offline after that. You can talk to it from a terminal dashboard, an HTTP/SSE API, or Signal.

## Decisions and trade-offs

### TUI first, desktop app as a preview, not the default path

The terminal dashboard is the default onboarding surface today; a Dioxus desktop app exists and can be installed as a preview from a source checkout, but it's explicitly the v1.0 target, not what a new user is pointed at first. The alternative — leading with the desktop app before it's ready for that role — would have shipped a worse first impression in exchange for a flashier README. The project didn't take that trade.

### One binary over an external-database architecture

Persistent memory, session state, and the knowledge graph all live inside the single binary rather than behind a Postgres or Redis dependency. The trade-off is real: an external database would have made some queries easier to reason about and easier to inspect with off-the-shelf tooling. The single-binary model wins instead because it's what makes "no containers, no sidecars" true rather than aspirational — the deployment story only stays that simple if the data layer doesn't reach outside the process.

### Runtime guardrails as a first-class layer, not an afterthought

Every tool call carries an HMAC-SHA256 receipt, and loop detection combines three separate signals (ping-pong, no-progress, and doom-loop patterns) rather than one heuristic. Per-stage timeouts bound how long any single turn can run. This is infrastructure a smaller project would have skipped until something broke in production; here it's part of the base runtime.

## What's solid / what's open

**Solid:** persistent memory and working-memory continuity across sessions, multi-agent coordination, the built-in tool plane (file I/O, shell execution, web search, memory search, planning, agent coordination), the TUI, the HTTP/SSE API, Signal messaging with `!`-prefixed operator commands that don't consume LLM tokens, and the runtime guardrail layer described above.

**Open:** the desktop app is a v1.0-target preview, not the default path — it's installed separately from a source checkout today. The MCP bridge for runtime-discovered external tools is opt-in (`--features mcp`), not compiled in by default. Several capability groups (`energeia`, `bookkeeper`, `computer-use`, `z3`) are feature-gated additions layered on top of the base tool set, not universal defaults.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Method | Where to check |
|---|---|---|
| 548,531 lines Rust (code-only), 620,898 including comments | `tokei` against a local clone HEAD, 2026-07-20 | reproducible: `tokei` on a fresh clone |
| 30 workspace crates | crate count in the workspace `Cargo.toml` | reproducible on a fresh clone |
| ~12,094 test-attribute occurrences | `rg -c '#\[(tokio::)?test'`, 2026-07-20 | reproducible: same `rg` command on a fresh clone |
| No telemetry, no phone-home, no crash reports | stated network posture, enumerated | `docs/NETWORK.md` in the repo — every outbound call the binary makes |

</div>

## Where to look

- Repo: [github.com/forkwright/aletheia](https://github.com/forkwright/aletheia)
- Architecture and current tool inventory: `docs/ARCHITECTURE.md`
- Every outbound network call the binary makes: `docs/NETWORK.md`
- The existing scripted demo (local model, no cloud key): `demo/README.md`
