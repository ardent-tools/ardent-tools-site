+++
title = "harmonia"
description = "A unified self-hosted media platform: one Rust server across 21 crates, replacing a stack of separate *arr-pattern services with one coherent media lifecycle manager."
weight = 6
template = "system.html"

[extra]
badge = "SHIPPED CORE · 2 STUBS AT HTTP LAYER"
repo = "https://github.com/forkwright/harmonia"
stack = "Rust · Tokio/Axum/SQLite · 21 workspace crates"
demo_len = "1:15"

[extra.headline_claim]
claim = "Shipped and wired to routes: auth, library import, feed scheduling, torrent download, queue orchestration, the streaming API"
receipt = "harmonia/README.md, capability-status table"

[extra.demo]
system = "harmonia"
action = "server boot, health check, library scan"
target = "seeded sample media only"
duration = "1:15"
placeholder = "RECORDING FORTHCOMING: harmonia serve boots → a health check answers → a library scan triggers → its import queue populates, against a small seeded sample-media directory"
shows = "A real server boot, a health check answering, and a library scan populating an import queue — the most product-shaped recording on this site."
not_shows = "The two HTTP-layer resolvers that are still null placeholders (metadata resolution and curation) — those are named directly in the solid/open list below, not hidden behind the demo."
+++

## What it is

harmonia is a unified self-hosted media platform: a single Tokio/Axum/SQLite server spanning 21 workspace crates, aimed at replacing the pattern where you run five or six separate *arr-style applications (one for movies, one for TV, one for music, one for indexing, one for requests) and wire them together yourself. Instead it's one coherent server covering the full media lifecycle: import and rename, library scanning, metadata enrichment, quality verification, torrent acquisition, download-queue orchestration, household request handling, HTTP streaming, and a native audio pipeline with bit-perfect decode and DSP.

## Decisions and trade-offs

### One server instead of five federated services

The *arr-stack pattern (a separate app per media type, each with its own database, its own auth, its own web UI, wired together by the user) is well-established and has a large plugin ecosystem behind it. harmonia rejects that shape on purpose: one server, one auth layer, one database, 21 crates organized by concern (core, auth, media ops, acquisition, serving, audio, UI) rather than by deployable unit. The cost is losing the *arr ecosystem's existing plugin surface; the benefit is a media manager that doesn't require reasoning about five services' worth of drift between each other.

### A capability table that names its own stubs, instead of one "it works" claim

Rather than describe the server as simply "working," the project's own documentation distinguishes shipped-and-wired-to-routes capabilities from initialized-but-adapter-backed-or-fallback-only ones, down to naming the exact count of remaining null placeholders. That's a harder thing to keep honest than a blanket status claim, and it's reproduced on this page rather than collapsed into something vaguer.

### Native audio pipeline instead of shelling out to an external decoder

The audio layer (`akouo-core`) does bit-perfect decode and its own DSP — EQ, crossfeed, ReplayGain — natively rather than piping through an external tool. On Linux this pulls in ALSA development headers at build time (a real, stated prerequisite, not hidden in a "just works" claim); the trade-off buys tighter control over the exact signal path from decode to output.

## What's solid / what's open

**Solid, shipped and wired to live routes:** auth, library scan/import, the feed scheduler, the torrent download engine, queue orchestration, the HTTP/OpenSubsonic streaming API, external integrations (Plex, Last.fm, Tidal), QUIC renderer transport, the native audio pipeline, and post-download import — a completed download lands directly in the library for music, movie, and book wants.

**Open:** two null placeholders remain at the HTTP layer, for metadata resolution and curation, on the live `serve` path — named directly, not folded into a vaguer "still improving" claim. Audiobook, comic, podcast, and TV-series wants have no library type yet and are deferred. A fallback/test path (`AppState::with_stubs`) defines nine additional `Null*` service implementations used for testing, separate from the two live-path placeholders above.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Method | Where to check |
|---|---|---|
| 100,460 lines Rust (code-only), 117,575 including comments | `tokei` against a local clone, 2026-07-20 | reproducible: `tokei` on a fresh clone |
| 21 workspace crates | crate count in the workspace `Cargo.toml` | reproducible on a fresh clone |
| ~2,290 test-attribute occurrences | `rg -c '#\[(tokio::)?test'`, 2026-07-20 | reproducible: same `rg` command on a fresh clone |
| 2 null placeholders remain at the live HTTP layer (metadata resolution, curation) | stated directly in the repo's own capability-status table | `README.md`, Capability status section |

</div>

## Where to look

- Repo: [github.com/forkwright/harmonia](https://github.com/forkwright/harmonia)
- The shipped-vs-stubbed capability table in full: `README.md`
- The CLI entry point (`serve`, `db`, `play`, `render`, `migrate`, local `mcp`): `crates/archon/src/cli.rs`
