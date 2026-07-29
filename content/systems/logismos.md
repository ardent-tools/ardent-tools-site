+++
title = "logismos"
description = "A GPU inference stack for transformer embedding models, built from the device upward in Rust and HIP for AMD hardware. CPU correctness proven. GPU cutover waits on hardware access."
weight = 6
template = "system.html"

[extra]
gloss = "λογισμός - reasoning, calculation"
badge = "PHASE 4 BLOCKED ON HARDWARE"
repo = "https://github.com/forkwright/logismos"
stack = "Rust · HIP/hipBLASLt · AMD gfx1100"
kanon_ci = true
license = "PolyForm Shield 1.0.0"

[extra.headline_claim]
claim = "Phases 0-3 complete - Stella 1.5B v5 runs end-to-end on CPU with golden-fixture parity"
receipt = "cargo test -p logismos --test phase_3_stella_parity -- --ignored, with /models/stella-1.5b-v5 present"

[extra.demo]
system = "logismos"
action = "CPU golden-fixture parity test"
target = "phase_3_stella_parity, against embeddings_dim1024.safetensors"
tape = "/tapes/logismos-parity.tape"
shows = "The ignored parity test executing on CPU with `/models/stella-1.5b-v5` available, rather than a zero-test green exit."
not_shows = "Any GPU run. Phase 4 remains hardware-blocked."
+++

## What it is

Candle has no ROCm backend, and AMD deprecated ONNX Runtime's ROCm support, so logismos builds the stack from the device upward in Rust and HIP, targeting the gfx1100 architecture (the W7900).

## Decisions and trade-offs

### Build the correctness harness before the GPU is available to prove performance

Phases 0 through 3 are complete and CPU-verified. Stella 1.5B v5 runs end-to-end on CPU with parity against a committed golden fixture. Phase 4, the GPU cutover, is blocked on hardware - the AMD W7900 host used for this work is down for recovery, so GPU code paths are unverified until it returns.

| Decision | Chose | Rejected | Cost accepted |
|---|---|---|---|
| Scope boundary | Tensor ops on HIP, transformer inference, Stella 1.5B end to end, the `EmbeddingModel` contract - named explicitly | Growing into training, non-AMD GPUs, runtime graph optimization, multi-GPU | Not reusable for training, non-AMD GPUs, or multi-GPU without new work |
| Framework scope | Scoped exactly to the knowledge substrate's actual consumer need | Building a general-purpose inference framework | Less reusable for a different model or a different GPU vendor |

## What's solid / what's open

**Solid:** Phases 0 through 3 - the full CPU inference path for Stella 1.5B, verified against a committed golden fixture. The parity test is marked `#[ignore]`. The proof command must include `-- --ignored`, and it requires the Stella model at `/models/stella-1.5b-v5`.

**Open:** Phase 4, the GPU cutover, is blocked on hardware. The AMD W7900 host this work targets is down for recovery. GPU-specific code paths exist but are unverified until it's back.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Reproduction method | Where to check |
|---|---|---|
| CPU golden-fixture parity test executes | `cargo test -p logismos --test phase_3_stella_parity -- --ignored` with `/models/stella-1.5b-v5` present; reject output reporting zero executed tests | `phases/03-stella/golden/embeddings_dim1024.safetensors` and the ignored test in the repo |
| Three GPU test targets exist and no workflow runs them | `crates/hipcore/tests/device_smoke.rs` and `crates/kernels/tests/{matmul_parity,op_parity}.rs` are present, and no workflow declares a gfx1100 or ROCm runner | `.github/workflows/` at `94e4e97dce6e` |
| 10,947 Rust code lines; 12,689 physical Rust lines | `tokei -o json . | jq '.Rust | {code, comments, blanks, physical: (.code + .comments + .blanks)}'` at `94e4e97dce6e`, 2026-07-20 | run from that revision |
| 27 Cargo workspace members | `cargo metadata --no-deps --format-version 1 | jq '.workspace_members | length'` at `94e4e97dce6e` | run from that revision |

</div>

## Where to look

- Repo: [github.com/forkwright/logismos](https://github.com/forkwright/logismos)
- The scoping decision, in the project's own words: `README.md`, Why and Scope sections
- The CPU correctness harness: `crates/logismos/tests/phase_3_stella_parity.rs`, `crates/embed/benches/stella_throughput.rs`
