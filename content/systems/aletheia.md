+++
title = "aletheia"
description = "Self-hosted AI agents with persistent memory. One binary, no containers, no external databases — a knowledge graph that carries forward across sessions."
weight = 2
template = "system.html"

[extra]
badge = "TUI DEFAULT · DESKTOP IN PREVIEW"
repo = "https://github.com/forkwright/aletheia"
stack = "Rust · single binary · Datalog-backed memory"
kanon_ci = true

[extra.headline_claim]
claim = "One binary — no containers, no external databases, no sidecars"
receipt = "aletheia/README.md, Architecture section"

[extra.demo]
system = "aletheia"
action = "memory recall across turns"
target = "local model, no cloud key"
tape = "/tapes/aletheia-memory.tape"
shows = "A fact stated in turn 1, recalled correctly and cited back in turn 3, running against a local model with no cloud API key."
not_shows = "The desktop app — it is a v1.0-target preview installed separately from source, not the default onboarding path."
+++

## What it is

aletheia is a self-hosted runtime for AI agents that remember. An agent carries the conversation forward: what was said last week, preferences stated once, a knowledge graph it builds from every session rather than starting cold each time. Each agent gets its own character, goals, and memory, and agents can coordinate with each other.

It ships as a single binary — no containers, no external database, no sidecar processes. Its network posture is narrower than “offline”: the runtime makes zero unsolicited outbound connections. Fully offline operation requires a local LLM, cached model files, and network tools and messaging channels disabled. It is reachable from a terminal dashboard, an HTTP/SSE API, or Signal when those interfaces are enabled.

## Decisions and trade-offs

### One binary over an external-database architecture

Persistent memory, session state, and the knowledge graph all live inside the single binary rather than behind a Postgres or Redis dependency. The trade-off is real: an external database would have made some queries easier to reason about and easier to inspect with off-the-shelf tooling.

| Decision | Chose | Rejected | Cost accepted |
|---|---|---|---|
| Onboarding surface | TUI dashboard as the default; a Dioxus desktop app installable as a preview | Leading with the desktop app before it's v1.0-ready | Desktop app requires a source checkout, not what a new user sees first |
| Guardrail layer | HMAC-SHA256 tool-call receipts, three-signal loop detection, per-stage timeouts, built into the base runtime | Adding guardrails later, once something breaks in production | More runtime infrastructure carried from day one, ahead of any real-world failure that proves it's needed |

## What's solid / what's open

**Solid:** persistent memory and working-memory continuity across sessions, multi-agent coordination, the built-in tool plane (file I/O, shell execution, web search, memory search, planning, agent coordination), the TUI, the HTTP/SSE API, Signal messaging with `!`-prefixed operator commands that don't consume LLM tokens, and the runtime guardrail layer described above.

**Open:** the desktop app is a v1.0-target preview, not the default path — it's installed separately from a source checkout today. The MCP bridge for runtime-discovered external tools is opt-in (`--features mcp`), not compiled in by default. Several capability groups (`energeia`, `bookkeeper`, `computer-use`, `z3`) are feature-gated additions layered on top of the base tool set, not universal defaults.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Method | Where to check |
|---|---|---|
| 550,578 Rust code lines; 623,250 physical Rust lines | `tokei` snapshot at `main` `1a0ee8a29cb2`, 2026-07-22 | reproducible: `tokei` on that commit |
| 49 Cargo workspace members | `cargo metadata --no-deps` at the same commit | reproducible on that commit |
| 12,133 test-attribute occurrences | `rg -o '#\[(tokio::)?test' --glob '*.rs' | wc -l` at the same commit, 2026-07-22 | reproducible: same pipeline |
| Zero unsolicited outbound connections; fully offline only with local LLM, cached models, and network tools/channels disabled | enumerated network posture | `docs/NETWORK.md` in the repo |

</div>

## Where to look

- Repo: [github.com/forkwright/aletheia](https://github.com/forkwright/aletheia)
- Architecture and current tool inventory: `docs/ARCHITECTURE.md`
- Every outbound network call the binary makes: `docs/NETWORK.md`
- The existing scripted demo (local model, no cloud key): `demo/README.md`
