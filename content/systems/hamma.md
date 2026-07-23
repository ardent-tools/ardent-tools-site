+++
title = "hamma"
description = "A clean-room Rust implementation of a Tailscale-compatible mesh networking stack. Pre-alpha, actively implementing the peer client against a real reference control plane."
weight = 7
template = "system.html"

[extra]
badge = "PRE-ALPHA"
repo = "https://github.com/forkwright/hamma"
stack = "Rust · Noise protocol · WireGuard data plane planned"
kanon_ci = true

[extra.headline_claim]
claim = "Noise handshake, control-protocol types, and TCP/TLS registration land in Phase A"
receipt = "hamma/README.md, Status section"

[extra.demo]
system = "hamma"
action = "handshake + control-protocol type tests"
target = "hamma-core, dictyon"
tape = "/tapes/hamma-tests.tape"
shows = "The Noise-handshake and control-protocol-type tests passing — modest, explicitly test-suite-shaped, matching where the project actually is."
not_shows = "Two peers joining a tailnet. The WireGuard data plane is not wired in."
+++

## What it is

No production-grade Rust implementation of Tailscale's protocol exists. hamma is built to fill that gap — the pieces needed to knot a set of devices into one flat network, speak WireGuard peer-to-peer, traverse NATs through DERP relays, and name each other through MagicDNS. It targets wire compatibility with the existing control plane, so a device running hamma can join the same tailnet as a device running the reference client. The work serves this practice's own systems first, and openly, anyone who wants a memory-safe, auditable mesh client.

## Decisions and trade-offs

### Clean-room, not a port

hamma is written from the protocol specification and public behavior, not translated line-by-line from Tailscale's Go client. Its current workspace denies unsafe code. BoringTun is only a commented Cargo placeholder for the planned WireGuard data plane, not a present dependency or a source of current unsafe code. The trade-off: a clean-room implementation is slower to reach feature parity than a direct port would be, since nothing gets carried over for free.

| Decision | Chose | Rejected | Cost accepted |
|---|---|---|---|
| Validation order | Validate `dictyon` against Tailscale's actual production control plane first | Building the self-hosted `histos` server first | No self-hosted option yet; Phase A depends on the vendor's control plane |
| Feature scope | Peer WireGuard, MagicDNS, exit nodes, ACLs | Matching Tailscale's full feature surface (Taildrop, SSH, Funnel, app connectors) | Real features left out until there's demand, not built speculatively |

## What's solid / what's open

**Solid:** the Noise handshake, control-protocol types, TCP/TLS registration, and the map-streaming loop, all landed as part of Phase A's `dictyon` peer client.

**Open, stated as the repo itself states it:** pre-alpha, no releases yet, no stable API. The next implementation milestone is the WireGuard data plane via BoringTun — the dependency itself has not landed, and until the data plane lands there's no working end-to-end tailnet. An open audit backlog tracks known gaps in map deltas, frame handling, node-key expiry, tracing, and map-stream integration coverage.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Reproduction method | Where to check |
|---|---|---|
| 4,091 Rust code lines; 5,112 physical Rust lines | `tokei -o json . | jq '.Rust | {code, comments, blanks, physical: (.code + .comments + .blanks)}'` at `216e2adc83d5`, 2026-07-20 | run from that revision |
| 2 Cargo workspace members (`dictyon` peer client, `hamma-core` shared types) | `cargo metadata --no-deps --format-version 1 | jq '.workspace_members | length'` at `216e2adc83d5` | run from that revision |

</div>

Smallest of the systems on this site — the newest and least mature.

## Where to look

- Repo: [github.com/forkwright/hamma](https://github.com/forkwright/hamma)
- Design principles, in the project's own words: `README.md`
- The peer client: `crates/dictyon/`; shared protocol types: `crates/hamma-core/`
