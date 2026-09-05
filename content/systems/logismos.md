+++
title = "logismos"
description = "GPU compute for an agent-aware operating environment for local AI compute. The Rust and AMD foundation has a CPU model path; GPU qualification is next."
weight = 6
template = "system.html"

[extra]
gloss = "λογισμός - reasoning, calculation"
badge = "GPU QUALIFICATION NEXT"
repo = "https://github.com/forkwright/logismos"
stack = "Rust · HIP/hipBLASLt · AMD gfx1100"
kanon_ci = true
license = "PolyForm Shield 1.0.0"

[extra.headline_claim]
claim = "CPU model path and golden-fixture harness present; GPU qualification has not run"
receipt = "The ignored parity harness is in crates/logismos/tests/phase_3_stella_parity.rs; its GPU counterpart remains unrun"

[extra.demo]
system = "logismos"
action = "CPU golden-fixture parity test"
target = "phase_3_stella_parity, against embeddings_dim1024.safetensors"
tape = "/tapes/logismos-parity.tape"
shows = "The retained CPU-parity recording target; it is historical evidence, not a current GPU qualification result."
not_shows = "Any GPU run, scheduler, serving surface, GDN, emulator, HSA integration, or multi-GPU service. GPU qualification has not run yet."
+++

## What it is

Agent intent is intended to pass through placement and residency decisions to native kernels. The greenfield Rust and AMD stack targets gfx1100, using HIP and hipBLASLt where the hardware boundary requires them. It provides the GPU-compute layer for an agent-aware operating environment for local AI compute.

## Decisions and trade-offs

### Establish the CPU model path before hardware qualification

The foundation and CPU model path exist, including a golden-fixture parity harness. The W7900 with 48 GB is the working hardware baseline and is available for qualification. That qualification has not run. GPU-safe emulation is planned; it does not establish device behavior.

| Decision | Chose | Rejected | Cost accepted |
|---|---|---|---|
| First delivery | Text and retrieval on one GPU | Training, non-AMD GPUs, automatic cutover | A second GPU does not change the first delivery boundary |
| Hardware baseline | gfx1100 on the available W7900 48 GB | Calling qualification complete before a device run | Hardware capability still needs qualification |
| Future topology | An XTX 24 GB as a planned, separately qualified second card | A 72 GB unified device or implicit sharding | Independent dual-GPU services require explicit work and verification |
| Framework scope | Scoped exactly to the knowledge substrate's actual consumer need | Building a general-purpose inference framework | Less reusable for a different model or a different GPU vendor |

## What's solid / what's open

**Current:** the Rust and AMD foundation, CPU model path, and ignored golden-fixture harness. The retained CPU-parity tape remains part of the record.

**Open:** hardware qualification on the W7900 baseline. Scheduling, serving, GDN, emulator work, and HSA integration are planned or in progress, not delivered. The first service boundary is text and retrieval on one GPU. A future XTX 24 GB card is not installed; when present, it needs separate qualification before independent dual-GPU services can run. There is no automatic cutover, 72 GB unified memory, or sharding claim.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Reproduction method | Where to check |
|---|---|---|
| CPU model path and golden-fixture harness are present | inspect `crates/logismos/tests/phase_3_stella_parity.rs` and `phases/03-stella/golden/embeddings_dim1024.safetensors` | the logismos repository |
| GPU qualification remains open | inspect the device-smoke and kernel-parity targets; no current qualification result is published | `crates/hipcore/tests/device_smoke.rs` and `crates/kernels/tests/{matmul_parity,op_parity}.rs` |
| First delivery is single-GPU text and retrieval | compare this delivery boundary with the planned second-card entry above | this system record |
| 10,947 Rust code lines; 12,689 physical Rust lines | `tokei -o json . | jq '.Rust | {code, comments, blanks, physical: (.code + .comments + .blanks)}'` at `94e4e97dce6e`, 2026-07-20 | run from that revision |
| 27 Cargo workspace members | `cargo metadata --no-deps --format-version 1 | jq '.workspace_members | length'` at `94e4e97dce6e` | run from that revision |

</div>

## Where to look

- Repo: [github.com/forkwright/logismos](https://github.com/forkwright/logismos)
- The scoping decision, in the project's own words: `README.md`, Why and Scope sections
- The CPU correctness harness: `crates/logismos/tests/phase_3_stella_parity.rs`, `crates/embed/benches/stella_throughput.rs`
