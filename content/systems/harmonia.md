+++
title = "harmonia"
description = "A unified self-hosted media platform: one Rust server across 21 crates, replacing a stack of separate *arr-pattern services with one coherent media lifecycle manager."
weight = 4
template = "system.html"

[extra]
badge = "SHIPPED CORE · LIVE ADAPTERS WIRED"
repo = "https://github.com/forkwright/harmonia"
stack = "Rust · Tokio/Axum/SQLite · 21 workspace members"
kanon_ci = true

[extra.headline_claim]
claim = "Shipped and wired to routes: auth, library import, feed scheduling, torrent download, queue orchestration, the streaming API"
receipt = "harmonia/README.md, capability-status table"

[extra.demo]
system = "harmonia"
action = "disposable server boot and health check"
target = "public /api/system/health route"
tape = "/tapes/harmonia-serve.tape"
shows = "A real server boot from disposable configuration and SQLite state, followed by the public health route returning its documented `status: ok` response."
not_shows = "A library scan or import. The current admin-protected `POST /api/library/scan` route returns 202 without performing a scan."
+++

## What it is

Running a self-hosted media stack usually means five or six separate *arr-style applications - one for movies, one for TV, one for music, one for indexing, one for requests - each with its own database and auth, wired together by hand. harmonia collapses that pattern into one server. A single Tokio/Axum/SQLite process, 21 Cargo workspace members, covering the full media lifecycle - import and rename, library scanning, metadata enrichment, quality verification, torrent acquisition, download-queue orchestration, household requests, HTTP streaming, and a native audio pipeline with bit-perfect decode and DSP.

## Decisions and trade-offs

### One server instead of five federated services

The *arr-stack pattern (a separate app per media type, each with its own database, its own auth, its own web UI, wired together by the user) is well-established and has a large plugin ecosystem behind it. harmonia rejects that shape on purpose: one server, one auth layer, one database, 21 crates organized by concern (core, auth, media ops, acquisition, serving, audio, UI) rather than by deployable unit. The cost is losing the *arr ecosystem's existing plugin surface.

| Decision | Chose | Rejected | Cost accepted |
|---|---|---|---|
| Status reporting | A capability table naming shipped-and-wired vs. stubbed capabilities, down to the exact stub count | A blanket "it works" status claim | Harder to keep honest than a vague claim - the count has to stay current |
| Audio decode | Native bit-perfect decode and DSP (`akouo-core`), in-process | Piping through an external decoder tool | ALSA development headers required at build time on Linux, a real stated prerequisite |

## What's solid / what's open

**Solid, shipped and wired to live routes:** auth, library read/import surfaces, the feed scheduler, the torrent download engine, queue orchestration, the HTTP/OpenSubsonic streaming API, external integrations (Plex, Last.fm, Tidal), QUIC renderer transport, the native audio pipeline, and post-download import - a completed download lands directly in the library for music, movie, and book wants.

**Solid, on the live serve path:** `serve` wires `metadata_adapter` and `CurationAdapter(DefaultCurationService)`. The earlier metadata and curation null-resolver claim is no longer true. Audiobook, comic, podcast, and TV library types exist alongside the established media paths.

**Open:** `AppState::with_stubs` remains a fallback and test constructor with ten `Null*` implementations. Those stubs are not the live `serve` wiring. At pinned revision `6ab797f81c31`, the admin-protected `POST /api/library/scan` handler returns `202 Accepted` without initiating a scan, so neither this page nor the recording plan treats it as scan evidence. The README documents build and test commands but not yet a day-to-day quick start or example configuration. Reaching a running instance from a fresh clone still means reading the `archon` CLI's own `--help` output.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Reproduction method | Where to check |
|---|---|---|
| 100,473 Rust code lines; 117,589 physical Rust lines | `tokei -o json . | jq '.Rust | {code, comments, blanks, physical: (.code + .comments + .blanks)}'` at `6ab797f81c31`, 2026-07-22 | run from that revision |
| 21 Cargo workspace members | `cargo metadata --no-deps --format-version 1 | jq '.workspace_members | length'` at `6ab797f81c31` | run from that revision |
| 2,290 test-attribute occurrences | `rg -o '#\[(tokio::)?test' --glob '*.rs' | wc -l` at `6ab797f81c31`, 2026-07-22 | run from that revision |
| Live `serve` wires metadata and curation adapters; fallback `with_stubs` has 10 `Null*` implementations | inspect constructors and serve wiring | `crates/archon` application state and serve path |

</div>

## Where to look

- Repo: [github.com/forkwright/harmonia](https://github.com/forkwright/harmonia)
- The shipped-vs-stubbed capability table in full: `README.md`
- The CLI entry point (`serve`, `db`, `play`, `render`, `migrate`, local `mcp`): `crates/archon/src/cli.rs`
