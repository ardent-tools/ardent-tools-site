+++
title = "logismos"
description = "A GPU inference stack for transformer embedding models, built from the device upward in Rust and HIP for AMD hardware. CPU correctness proven; GPU cutover waits on hardware access."
weight = 6
template = "system.html"

[extra]
badge = "PHASE 4 BLOCKED ON HARDWARE"
repo = "https://github.com/forkwright/logismos"
stack = "Rust · HIP/hipBLASLt · AMD gfx1100"
demo_len = "1:00"

[extra.headline_claim]
claim = "Phases 0-3 complete — Stella 1.5B v5 runs end-to-end on CPU with golden-fixture parity"
receipt = "logismos/README.md status line; crates/logismos/tests/phase_3_stella_parity.rs"

[extra.demo]
system = "logismos"
action = "CPU golden-fixture parity test"
target = "phase_3_stella_parity, against a committed fixture"
duration = "1:00"
tape = "/tapes/logismos-parity.tape"
placeholder = "RECORDING FORTHCOMING: cargo test -p logismos --test phase_3_stella_parity passing against the committed CPU baseline fixture"
shows = "The correctness harness passing on CPU, against a fixture committed to the repo — proof the inference path is correct independent of GPU hardware."
not_shows = "Any GPU run. Phase 4 is hardware-blocked; this recording won't stage one to imply otherwise."
+++

## What it is

logismos is a GPU inference stack for transformer embedding models, built from the device upward in Rust and HIP, targeting AMD's gfx1100 architecture (the W7900). It exists because the alternatives didn't: Candle has no ROCm backend, and AMD deprecated ONNX Runtime's ROCm support. Rolling this from scratch keeps the hardware boundary owned in-repo instead of depending on either gap closing upstream.

## Decisions and trade-offs

### Build the correctness harness before the GPU is available to prove performance

Phases 0 through 3 are complete and CPU-verified: Stella 1.5B v5 runs end-to-end on CPU with parity against a committed golden fixture. Phase 4, the GPU cutover, is blocked on hardware — the AMD W7900 host used for this work is down for recovery, so GPU code paths are unverified until it returns. Rather than treat that as a reason to stop, the project used the wait to build and lock in a CPU correctness harness first. A team without that discipline would have GPU code with nothing to check it against once hardware access resumed; this one has a golden fixture already waiting.

### Explicit scope discipline, stated as boundaries rather than left implicit

In scope: tensor operations on HIP, transformer inference, Stella 1.5B end to end, and the `EmbeddingModel` contract the fleet's knowledge substrate consumes. Explicitly out of scope: training, non-AMD GPUs, runtime graph optimization, multi-GPU. Each of those exclusions is a real capability logismos could have grown toward; naming them as out-of-scope up front is what keeps a 27-crate, ~11K-line project that small on purpose instead of by accident.

### One transformer family, one GPU family, not a general-purpose framework

The project is scoped to exactly what its consumer (a knowledge substrate needing a GPU-accelerated embedder) needs, not built as a general inference framework that happens to support that case. The trade-off: less reusable for someone with a different model or a different GPU vendor. The benefit: nothing in the design is generalized past what's actually been built and tested.

## What's solid / what's open

**Solid:** Phases 0 through 3 — the full CPU inference path for Stella 1.5B, verified against a committed golden fixture, with the exact parity test anyone can run.

**Open, stated plainly rather than hidden:** Phase 4, the GPU cutover, is blocked on hardware. The AMD W7900 host this work targets is down for recovery; GPU-specific code paths exist but are unverified until it's back. This is a hardware-availability blocker, not a code-quality one — the CPU path it's blocked behind is the thing this page can actually show working.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Method | Where to check |
|---|---|---|
| CPU golden-fixture parity test passes | `cargo test -p logismos --test phase_3_stella_parity` | `phases/03-stella/golden/` in the repo — the fixture itself |
| 10,947 lines Rust (code-only), 12,689 including comments | `tokei` against a local clone, 2026-07-20 | reproducible: `tokei` on a fresh clone |
| 27 workspace crates, deliberately small and tightly scoped | crate count in the workspace `Cargo.toml` | reproducible on a fresh clone |

</div>

## Where to look

- Repo: [github.com/forkwright/logismos](https://github.com/forkwright/logismos)
- The scoping decision, in the project's own words: `README.md`, Why and Scope sections
- The CPU correctness harness: `crates/logismos/tests/phase_3_stella_parity.rs`, `crates/embed/benches/stella_throughput.rs`
