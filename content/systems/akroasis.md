+++
title = "akroasis"
description = "An RF signals toolkit in Rust: a clean-room Meshtastic mesh stack running live, CHIRP radio workflows, an encrypted credential vault, and a 17-domain signal model labeled by what actually ships."
weight = 5
template = "system.html"

[extra]
badge = "MESH LIVE · 11 OF 17 DOMAINS PLANNED"
repo = "https://github.com/forkwright/akroasis"
stack = "Rust workspace · 7 crates · AGPL-3.0"
demo_len = "0:50"

[extra.headline_claim]
claim = "A clean-room Meshtastic stack is the live signal producer"
receipt = "kerykeion: framing, serial/TCP transports, encryption, routing, store-and-forward · crates/kerykeion"

[extra.demo]
system = "akroasis"
action = "CHIRP import, then vault verify"
target = "akroasis radio import / vault identity"
duration = "0:50"
placeholder = "RECORDING FORTHCOMING: CHIRP CSV import, validation, Baofeng UV-5R export, then vault identity and tamper-log check — the CLI paths that run today, no radio hardware in frame"
shows = "Real CLI sessions against the shipped crates: syntonia's CHIRP workflow and kryphos's vault, --json output included."
not_shows = "Live mesh traffic or radio programming. The mesh CLI is static until daemon mode lands, and radio read/program waits on the protocol session backend. StubHardware is the default; the caption says so."
+++

## What it is

Radio, mesh networking, and spectrum-monitoring tools tend to be separate interfaces with separate data models. akroasis folds them into one Rust workspace instead: a typed signal model shared across domains, so a mesh node going quiet and a frequency spike nearby read as one event, not two unrelated logs. The mesh stack — a clean-room reimplementation of the Meshtastic protocol — runs live today. The rest is scored by what ships: kerykeion carries the mesh, syntonia handles radio programming, kryphos is the vault, and the shared signal model (its koinon crate) defines the typed contract the others write into. Everything runs offline, every protocol implemented in-repo rather than bound to a vendor library.

## Decisions and trade-offs

### The clean-room Meshtastic stack

kerykeion reimplements the protocol in Rust: protobuf framing, transports, encryption, the node database, routing, store-and-forward, rather than binding the vendor's firmware libraries. The cost is months rebuilding what a binding hands over for free; `cargo tree` confirms no upstream Meshtastic crate in the dependency graph. The return: the one domain that graduated from planned to live is inspectable and testable end to end, with no C++ under the safety-critical layer. The rejected alternative — wrapping the official library and inheriting its release cadence — was available and passed over.

| Decision | Chose | Rejected | Cost accepted |
|---|---|---|---|
| Signal model before collectors | A 7-domain typed signal contract, synthetic pipeline tests holding it | A schema grown per domain as collectors landed | 11 of 17 domains declared stubs, in public |
| Encrypted by default | Argon2id, ChaCha20-Poly1305, Ed25519, and a BLAKE3 hash-chain tamper log | Plaintext credentials, encryption as an opt-in | Vault commands stay TTY-interactive until service surfaces ship |

## What's solid / what's open

**Solid:** kerykeion end to end — protobuf framing, serial/TCP transports, handshake, encryption, the node database, topology, discovery, routing, delivery tracking, store-and-forward, a gateway bridge. syntonia's CHIRP CSV/IMG import, validation, and Baofeng UV-5R export, with opt-in live serial detection. The kryphos vault, with its tamper-evident mutation log beside the store. Typed JSON throughout: every CLI carries `--json`, and `akroasis-server` exposes the same surface over `/api/v1/*`.

**Open:** eleven of seventeen declared domains have no shipped code — the README's own table is the ledger. The mesh CLI is static until daemon mode lands. Radio read/program wait on a protocol session backend that doesn't exist yet; `StubHardware` is the default. Aggregation has one live producer; cross-domain convergence runs synthetic everywhere else. No build/test workflow runs on GitHub Actions — issue #262 says so, and this page won't imply otherwise while it's true.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Method | Where to check |
|---|---|---|
| Clean-room Meshtastic stack, live as the one production signal producer | Read the crate; `cargo tree -p kerykeion` shows no upstream Meshtastic crate | `crates/kerykeion` |
| 7 workspace crates shipped | `ls crates/` on a fresh clone | reproducible |
| 17 capability domains declared; 11 with no shipped code | Count rows and stub marks in the README table | `README.md` domain table |
| Vault mutations logged to a BLAKE3 hash-chain tamper log | kryphos dependency tree + the `tamper.log` contract | `crates/kryphos` |
| 23,569 lines Rust (code-only), 24,538 including comments | `tokei` against a local clone, 2026-07-21 | reproducible: `tokei` on a fresh clone |
| 809 test-attribute occurrences | `rg -c '#\[(tokio::)?test'`, 2026-07-21 | reproducible: same `rg` command on a fresh clone |
| No build/test workflow runs on Actions | Open issue #262 | issue #262 |

</div>

## Where to look

- Repo: [github.com/forkwright/akroasis](https://github.com/forkwright/akroasis)
- The mesh stack: `crates/kerykeion`
- The vault and its tamper log: `crates/kryphos`
- The domain table: shipped vs. planned, in the README
- The self-filed CI gap: [issue #262](https://github.com/forkwright/akroasis/issues/262)
