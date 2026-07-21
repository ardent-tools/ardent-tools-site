+++
title = "hamma"
description = "A clean-room Rust implementation of a Tailscale-compatible mesh networking stack. Pre-alpha, actively implementing the peer client against a real reference control plane."
weight = 7
template = "system.html"

[extra]
badge = "PRE-ALPHA"
repo = "https://github.com/forkwright/hamma"
stack = "Rust · WireGuard (boringtun) · Noise protocol"
demo_len = "0:45"

[extra.headline_claim]
claim = "Noise handshake, control-protocol types, and TCP/TLS registration land in Phase A"
receipt = "hamma/README.md, Status section"

[extra.demo]
system = "hamma"
action = "handshake + control-protocol type tests"
target = "hamma-core, dictyon"
duration = "0:45"
tape = "/tapes/hamma-tests.tape"
placeholder = "RECORDING FORTHCOMING: cargo test -p hamma-core && cargo test -p dictyon — the Noise-handshake and control-protocol-type tests passing"
shows = "The Noise-handshake and control-protocol-type tests passing — modest, explicitly test-suite-shaped, matching where the project actually is."
not_shows = "Two peers joining a tailnet. That moment doesn't exist yet — the WireGuard data plane isn't wired in; this recording won't stage a fake version of it."
+++

## What it is

hamma is a clean-room Rust implementation of a Tailscale-compatible mesh networking stack: the pieces needed to knot a set of devices into one flat network, speak WireGuard peer-to-peer, traverse NATs through DERP relays, and name each other through MagicDNS. It targets wire compatibility with Tailscale's existing control plane, so a device running hamma can join the same tailnet as a device running the reference client. It exists because no production-grade Rust implementation of that protocol exists yet, and it's meant to fill that gap both for this practice's own systems and openly, for anyone who wants a memory-safe, auditable mesh client.

## Decisions and trade-offs

### Clean-room, not a port

hamma is written from the protocol spec and public behavior, not translated line-by-line from Tailscale's Go client. No vendor blobs, no unsafe beyond what the underlying `boringtun` crate already audits. The trade-off: a clean-room implementation is slower to reach feature parity than a direct port would be, since nothing gets carried over for free. The reasoning: a port inherits whatever the original got wrong along with what it got right; a clean-room build only has to be correct against the wire protocol.

### Validate against the real control plane before building a self-hosted one

A self-hosted coordination server (`histos`, matching Headscale's role) is planned but not started. Phase A deliberately validates the `dictyon` peer client against Tailscale's actual production control plane first — proving the client works against a real reference implementation before any self-hosted server exists to hide behind. Building the self-hosted server first would have meant validating the client against infrastructure this project also controls, which proves less.

### A deliberately small feature target

The scope is peer WireGuard, MagicDNS, exit nodes, and ACLs — explicitly not Taildrop, Tailscale SSH, Funnel, or app connectors. Those could be added later if there's real demand; they aren't being built speculatively now. Matching Tailscale's full feature surface was the available alternative, and it was rejected in favor of staying small until the core client is solid.

## What's solid / what's open

**Solid:** the Noise handshake, control-protocol types, TCP/TLS registration, and the map-streaming loop, all landed as part of Phase A's `dictyon` peer client.

**Open, stated as the repo itself states it:** pre-alpha, no releases yet, no stable API. The next implementation milestone is the WireGuard data plane via `boringtun` — until that lands, there's no working end-to-end tailnet, and this page won't imply otherwise. An open audit backlog tracks known gaps in map deltas, frame handling, node-key expiry, tracing, and map-stream integration coverage.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Method | Where to check |
|---|---|---|
| 4,091 lines Rust (code-only), 5,112 including comments | `tokei` against a local clone, 2026-07-20 | reproducible: `tokei` on a fresh clone |
| 2 workspace crates (`dictyon` peer client, `hamma-core` shared types) | crate count in the workspace `Cargo.toml` | reproducible on a fresh clone |

</div>

Smallest of the systems on this site, by design — the newest and least mature, not padded to look bigger than it is.

## Where to look

- Repo: [github.com/forkwright/hamma](https://github.com/forkwright/hamma)
- Design principles, in the project's own words: `README.md`
- The peer client: `crates/dictyon/`; shared protocol types: `crates/hamma-core/`
