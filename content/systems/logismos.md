+++
title = "logismos"
description = "An agent-aware operating environment for local AI compute, under development in Rust for AMD gfx1100. CPU model parity exists; native text serving remains open."
weight = 6
template = "system.html"

[extra]
gloss = "λογισμός - reasoning, calculation"
badge = "GPU QUALIFICATION NEXT"
repo = "https://github.com/forkwright/logismos"
stack = "Rust · HIP/WMMA · AMD gfx1100"
kanon_ci = true
license = "LicenseRef-PolyForm-Noncommercial-1.0.0"

[extra.headline_claim]
claim = "Stella CPU golden-fixture parity recorded; native text serving remains unqualified"
receipt = "The CPU reproduction target is crates/logismos/tests/phase_3_stella_parity.rs; this evidence does not qualify a GPU serving runtime"

[extra.demo]
system = "logismos"
action = "CPU golden-fixture parity test"
target = "phase_3_stella_parity, against embeddings_dim1024.safetensors"
tape = "/tapes/logismos-parity.tape"
shows = "The retained CPU-parity recording target; it is historical evidence, not a current GPU qualification result."
not_shows = "A GPU serving run, scheduler, GDN, emulator, HSA integration, or multi-GPU service. These require separate evidence."
+++

## What it is

Logismos is under development as an agent-aware operating environment for local AI compute. Aletheia supplies workload intent; Logismos is to own inference admission, placement and residency through to native execution. The Rust foundation targets gfx1100 through HIP and owned WMMA kernels. Host modes, display ownership and external service lifecycle stay with Arche/Tropos and systemd.

## Decisions and trade-offs

### Establish the CPU model path before hardware qualification

Stella CPU golden-fixture parity is recorded in the project history. Earlier W7900 kernel measurements are evidence for those kernels, not for the new serving program. The available W7900 48 GB remains the single-device baseline. Agent-led iteration uses GPU-denied checks; the original bounded emulator is under development and cannot establish hardware timing or performance.

| Decision | Chose | Rejected | Cost accepted |
|---|---|---|---|
| First delivery | Text and retrieval on one GPU | Training, non-AMD GPUs, automatic cutover | A second GPU does not change the first delivery boundary |
| Hardware baseline | gfx1100 on the available W7900 48 GB | Calling qualification complete before a device run | Hardware capability still needs qualification |
| Future topology | An XTX 24 GB as a planned, separately qualified second card | A 72 GB unified device or implicit sharding | Independent dual-GPU services require explicit work and verification |
| Runtime scope | Agent-aware inference, with ordinary inference clients still supported | A general training framework or a second host-mode executor | Native model support needs artifact-specific correctness and quality evidence |

## What's solid / what's open

**Current:** the Rust and AMD foundation, Stella CPU model path, and golden-fixture parity record. The retained CPU-parity tape is a recording target, not a new measurement.

**Open:** Qwen3.8 hybrid text serving and Qwen3 embedding/reranking continuity, with exact artifacts and local quality evaluation. Planning, device selection and GPU-safe testing are the foundation increment; native serving and the experimental HSA provider still need implementation and qualification. A planned XTX 24 GB needs separate qualification before independent dual-GPU services can run. There is no automatic cutover, 72 GB unified memory, or sharding claim.

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
