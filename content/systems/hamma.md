+++
title = "hamma"
description = "A clean-room Rust implementation of a Tailscale-compatible mesh networking stack. Pre-alpha, actively implementing the peer client against a real reference control plane."
weight = 7
template = "system.html"

[extra]
gloss = "ἅμμα - a knot, a tie, a fastening"
badge = "PRE-ALPHA"
repo = "https://github.com/forkwright/hamma"
stack = "Rust · Noise protocol · WireGuard data plane planned"
kanon_ci = true
license = "MIT OR Apache-2.0"

[extra.headline_claim]
claim = "Noise handshake, control-protocol types, and TCP/TLS registration land in Phase A"
receipt = "connects_and_completes_noise_handshake and register_returns_authorized_with_preauth_key pass, 5/5 in crates/dictyon/tests/wire_integration.rs · /casts/hamma-tests.cast"

[extra.demo]
system = "hamma"
action = "handshake + control-protocol type tests"
target = "hamma-core, dictyon"
cast = "/casts/hamma-tests.cast"
recipe = "/tapes/hamma-tests.driver.sh"
duration = "19s"
cols = 80
rows = 24
poster = "npt:0:17"
shows = "The Noise-handshake and control-protocol-type tests passing - modest, explicitly test-suite-shaped, matching where the project actually is."
not_shows = "Two peers joining a tailnet - the WireGuard data plane is not wired in."
fallback = [
  "$ cargo test -p hamma-core && ok CORE_TESTS_OK",
  "test result: ok. 22 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s",
  "test result: ok. 12 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s",
  "HAMMA_CORE_TESTS_OK",
  "$ cargo test -p dictyon && ok DICTYON_TESTS_OK",
  "test result: ok. 39 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.21s",
  "test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.05s",
  "HAMMA_DICTYON_TESTS_OK",
  "$ # not shown: two peers on a tailnet - no wireguard data plane here",
]
transcript = '''
$ # hamma - current control-plane tests, not an end-to-end tailnet
$ git rev-parse --short=12 HEAD
2423485c5c48
$ cargo test -p hamma-core && ok CORE_TESTS_OK
    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.05s
     Running unittests src/lib.rs (/tmp/hamma-cast-target/debug/deps/hamma_core-1b024f9fbd4821c5)

running 22 tests
test config::tests::config_deserialises_from_partial_json ... ok
test config::tests::config_rejects_unknown_fields ... ok
test config::tests::default_values_match_documented_constants ... ok
test config::tests::key_response_max_bytes_is_derived ... ok
test config::tests::config_roundtrips_through_json ... ok
test config::tests::key_response_max_bytes_saturates_on_overflow ... ok
test keys::tests::different_keys_produce_different_public_keys ... ok
test keys::tests::from_bytes_round_trips ... ok
test keys::tests::generate_machine_key_produces_32_bytes ... ok
test keys::tests::disco_key_round_trips ... ok
test keys::tests::private_key_debug_redacts ... ok
test keys::tests::node_key_round_trips ... ok
test keys::tests::public_key_derivation_is_deterministic ... ok
test types::tests::map_response_deserializes_peer_changed_patch ... ok
test types::tests::map_response_deserializes_full ... ok
test types::tests::map_response_deserializes_keepalive ... ok
test keys::tests::to_hex_includes_prefix ... ok
test types::tests::map_response_deserializes_peer_removals_by_node_id_and_key ... ok
test types::tests::node_deserializes_with_optional_fields ... ok
test types::tests::register_request_serializes_to_json ... ok
test keys::tests::machine_key_hex_has_correct_format ... ok
test keys::tests::machine_key_hex_round_trips ... ok

test result: ok. 22 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/public_api.rs (/tmp/hamma-cast-target/debug/deps/public_api-12b73c23f0f53ba2)

running 12 tests
test machine_public_from_hex_rejects_missing_prefix ... ok
test dns_and_derp_types_reachable_through_public_api ... ok
test machine_public_from_hex_rejects_wrong_length ... ok
test map_request_round_trips_through_json ... ok
test map_response_deserializes_keepalive_only_frame ... ok
test key_hierarchy_types_are_constructible ... ok
test node_deserializes_minimal_fields ... ok
test machine_public_round_trips_through_hex ... ok
test peer_change_patch_type_is_public_api ... ok
test peer_removal_type_is_public_api ... ok
test register_response_parses_auth_url_variant ... ok
test register_request_omits_none_fields ... ok

test result: ok. 12 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

   Doc-tests hamma_core

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

HAMMA_CORE_TESTS_OK
$ cargo test -p dictyon && ok DICTYON_TESTS_OK
    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.09s
     Running unittests src/lib.rs (/tmp/hamma-cast-target/debug/deps/dictyon-2dc8a78c06e2617f)

running 39 tests
test control::tests::apply_map_response_applies_peer_patch_to_known_peer ... ok
test control::tests::apply_map_response_ignores_peer_patch_for_unknown_peer ... ok
test control::tests::apply_map_response_delta_adds_peers ... ok
test control::tests::apply_map_response_removes_peers ... ok
test control::tests::apply_map_response_removes_peers_by_node_id ... ok
test control::tests::apply_map_response_sets_initial_peers ... ok
test control::tests::parse_map_response_extracts_json ... ok
test control::tests::parse_map_response_extracts_zstd_json ... ok
test control::tests::parse_map_response_rejects_truncated_frame ... ok
test control::tests::keepalive_does_not_modify_netmap ... ok
test control::tests::register_builds_correct_json ... ok
test control::tests::map_request_advertises_zstd_compression ... ok
test noise::tests::handshake_initiation_produces_message ... ok
test control::tests::netmap_starts_empty ... ok
test noise::tests::initiation_frame_has_correct_structure ... ok
test noise::tests::handshake_full_ik_round_trip ... ok
test noise::tests::decrypt_wrong_key_fails ... ok
test noise::tests::noise_ik_handshake_completes ... ok
test noise::tests::process_response_rejects_wrong_type_byte ... ok
test noise::tests::process_response_rejects_truncated_frame ... ok
test noise::tests::noise_config_tightens_frame_payload_limit ... ok
test noise::tests::transport_encrypt_decrypt_round_trip ... ok
test noise::tests::transport_empty_payload_round_trips ... ok
test noise::tests::transport_encrypt_decrypt_round_trips ... ok
test noise::tests::transport_frame_has_correct_structure ... ok
test transport::tests::build_upgrade_request_sets_correct_headers ... ok
test transport::tests::build_upgrade_request_strips_trailing_slash ... ok
test wire::tests::parse_host_port_https_default ... ok
test wire::tests::parse_host_port_trailing_slash ... ok
test wire::tests::parse_host_port_with_explicit_port ... ok
test wire::tests::build_upgrade_request_contains_required_headers ... ok
test wire::tests::parse_server_key_response_extracts_key ... ok
test wire::tests::parse_server_key_response_missing_field_errors ... ok
test noise::tests::transport_max_payload_accepted ... ok
test transport::tests::send_encrypts_payload ... ok
test noise::tests::transport_decrypt_with_wrong_key_fails ... ok
test noise::tests::transport_oversized_payload_rejected ... ok
test noise::tests::transport_payload_round_trips ... ok
test control::tests::netmap_delta_sequence_is_consistent ... ok

test result: ok. 39 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.21s

     Running tests/wire_integration.rs (/tmp/hamma-cast-target/debug/deps/wire_integration-cbe6f5b5ed2ae63d)

running 5 tests
test connection_to_unreachable_host_returns_error ... ok
test fetch_server_key_parses_response ... ok
test connects_and_completes_noise_handshake ... ok
test map_stream_receives_compressed_full_map_after_register ... ok
test register_returns_authorized_with_preauth_key ... ok

test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.05s

   Doc-tests dictyon

running 1 test
test crates/dictyon/src/control/mod.rs - control::ControlClient (line 124) ... ignored

test result: ok. 0 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.00s

HAMMA_DICTYON_TESTS_OK
$ # not shown: two peers on a tailnet - no wireguard data plane here
'''
+++

## What it is

hamma speaks Tailscale's control protocol from the Rust side - the pieces needed to knot a set of devices into one flat network, speak WireGuard peer-to-peer, traverse NATs through DERP relays, and name each other through MagicDNS. It targets wire compatibility with the existing control plane, so a device running hamma can join the same tailnet as a device running the reference client. I build it for the systems in this fleet first. The license is MIT OR Apache-2.0, so anyone else can run it.

## Decisions and trade-offs

### Written from the specification

hamma is written from the protocol specification and public behavior, not translated line-by-line from Tailscale's Go client. Its current workspace denies unsafe code. BoringTun is only a commented Cargo placeholder for the planned WireGuard data plane, not a present dependency or a source of current unsafe code. A clean-room implementation is slower to reach feature parity than a direct port would be, since nothing gets carried over for free.

| Decision | Chose | Rejected | Cost accepted |
|---|---|---|---|
| Validation order | Validate `dictyon` against Tailscale's actual production control plane first | Building the self-hosted `histos` server first | No self-hosted option yet; Phase A depends on the vendor's control plane |
| Feature scope | Peer WireGuard, MagicDNS, exit nodes, ACLs | Matching Tailscale's full feature surface (Taildrop, SSH, Funnel, app connectors) | Real features left out until there's demand, not built speculatively |

## What's solid / what's open

**Solid:** the Noise handshake, control-protocol types, TCP/TLS registration, and the map-streaming loop, all landed as part of Phase A's `dictyon` peer client.

**Open, in the repo's own words:** pre-alpha, no releases yet, no stable API. The next implementation milestone is the WireGuard data plane via BoringTun - the dependency itself has not landed, and until the data plane lands there's no working end-to-end tailnet. An open audit backlog tracks known gaps in map deltas, frame handling, node-key expiry, tracing, and map-stream integration coverage.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Reproduction method | Where to check |
|---|---|---|
| 4,088 Rust code lines; 5,109 physical Rust lines | `tokei -o json . | jq '.Rust | {code, comments, blanks, physical: (.code + .comments + .blanks)}'` at `2423485c5c48`, 2026-07-24 | run from that revision |
| 2 Cargo workspace members (`dictyon` peer client, `hamma-core` shared types) | `cargo metadata --no-deps --format-version 1 | jq '.workspace_members | length'` at `2423485c5c48` | run from that revision |

| No WireGuard data plane: BoringTun is a commented placeholder, not a dependency | grep the workspace manifests for `boringtun` | `Cargo.toml` at `2423485c5c48` |

</div>

## Where to look

- Repo: [github.com/forkwright/hamma](https://github.com/forkwright/hamma)
- Design principles, in the project's own words: `README.md`
- The peer client: `crates/dictyon/`. Shared protocol types: `crates/hamma-core/`
