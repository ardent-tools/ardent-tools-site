+++
title = "akroasis"
description = "An RF signals toolkit in Rust: a clean-room Meshtastic mesh stack running live, CHIRP radio workflows, an encrypted credential vault, and a 17-domain signal model labeled by what actually ships."
weight = 5
template = "system.html"

[extra]
badge = "MESH LIVE · 11 OF 17 DOMAINS PLANNED"
repo = "https://github.com/forkwright/akroasis"
stack = "Rust workspace · 7 crates · AGPL-3.0-only"
license = "AGPL-3.0-only"
kanon_ci = true

[extra.headline_claim]
claim = "A clean-room Meshtastic stack is the live signal producer"
receipt = "kerykeion: framing, serial/TCP transports, encryption, routing, store-and-forward · crates/kerykeion"

[extra.demo]
system = "akroasis"
action = "CHIRP import, then vault verify"
target = "akroasis radio import / vault identity"
shows = "Real CLI sessions against the shipped crates: syntonia's CHIRP workflow and kryphos's vault, --json output included."
not_shows = "Live mesh traffic or radio programming. The mesh CLI is static until daemon mode lands, and radio read/program waits on the protocol session backend. StubHardware is the default; the caption says so."
+++

## What it is

Radio, mesh networking, and spectrum-monitoring tools tend to be separate interfaces with separate data models. akroasis folds them into one Rust workspace instead: a typed signal model shared across domains, so a mesh node going quiet and a frequency spike nearby read as one event, not two unrelated logs. The mesh stack - a clean-room reimplementation of the Meshtastic protocol - runs live today. The rest is scored by what ships: kerykeion carries the mesh, syntonia handles radio programming, kryphos is the vault, and the shared signal model (its koinon crate) defines the typed contract the others write into.

## Decisions and trade-offs

### The clean-room Meshtastic stack

kerykeion reimplements the protocol in Rust: protobuf framing, transports, encryption, the node database, routing, store-and-forward, rather than binding the vendor's firmware libraries. The cost is months rebuilding what a binding hands over for free. `cargo tree` confirms no upstream Meshtastic crate in the dependency graph. kerykeion is the one domain live end to end, with no C++ in the mesh protocol path. The rejected alternative - wrapping the official library and inheriting its release cadence - was available and passed over.

| Decision | Chose | Rejected | Cost accepted |
|---|---|---|---|
| Signal model before collectors | A 7-domain typed signal contract, synthetic pipeline tests holding it | A schema grown per domain as collectors landed | 11 of 17 domains declared stubs, in public |
| Encrypted by default | Argon2id, ChaCha20-Poly1305, Ed25519, and a BLAKE3 hash-chain tamper log | Plaintext credentials, encryption as an opt-in | Vault commands stay TTY-interactive until service surfaces ship |

## What's solid / what's open

**Solid:** kerykeion end to end - protobuf framing, serial/TCP transports, handshake, encryption, the node database, topology, discovery, routing, delivery tracking, store-and-forward, a gateway bridge. syntonia's CHIRP CSV/IMG import, validation, and Baofeng UV-5R export, with opt-in live serial detection. The kryphos vault, with its tamper-evident mutation log beside the store. Typed JSON runs throughout. Every CLI carries `--json`, and `akroasis-server` exposes the same surface over `/api/v1/*`.

**Open:** eleven of seventeen declared domains have no shipped code - the README's own table is the ledger. The mesh CLI is static until daemon mode lands. Radio read/program wait on a protocol session backend that doesn't exist yet. `StubHardware` is the default. Aggregation has one live producer, and cross-domain convergence runs synthetic everywhere else. No build/test workflow runs on GitHub Actions - issue #262 says so.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Reproduction method | Where to check |
|---|---|---|
| Clean-room Meshtastic stack, live as the one production signal producer | Read the crate; `cargo tree -p kerykeion` shows no upstream Meshtastic crate | `crates/kerykeion` |
| 7 Cargo workspace members | `cargo metadata --no-deps --format-version 1 | jq '.workspace_members | length'` at `4e3712669df7` | run from that revision |
| 17 capability domains declared; 11 with no shipped code | Count rows and stub marks in the README table | `README.md` domain table |
| Vault mutations logged to a BLAKE3 hash-chain tamper log | kryphos dependency tree + the `tamper.log` contract | `crates/kryphos` |
| 23,569 Rust code lines; 24,538 Rust code-plus-comment lines | `tokei -o json . | jq '.Rust | {code, comments, blanks, physical: (.code + .comments + .blanks)}'` at `4e3712669df7`, 2026-07-21; code plus comments yields 24,538 | run from that revision |
| 809 test-attribute occurrences | `rg -o '#\[(tokio::)?test' --glob '*.rs' | wc -l` at `4e3712669df7`, 2026-07-21 | run from that revision |
| No build/test workflow runs on Actions | Open issue #262 | issue #262 |

</div>

## Where to look

- Repo: [github.com/forkwright/akroasis](https://github.com/forkwright/akroasis)
- The mesh stack: `crates/kerykeion`
- The vault and its tamper log: `crates/kryphos`
- The domain table: shipped vs. planned, in the README
- The self-filed CI gap: [issue #262](https://github.com/forkwright/akroasis/issues/262)
