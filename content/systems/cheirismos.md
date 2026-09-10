+++
title = "cheirismos"
description = "A development-stage local control plane for agents that observe, experiment on, and manipulate physical computing devices under explicit, durable governance."
weight = 9
template = "system.html"

[extra]
gloss = "χειρισμός - deliberate handling"
badge = "ALPHA · FIXTURE QUALIFICATION PENDING"
repo = "https://github.com/forkwright/cheirismos"
stack = "Rust · local supervisor · SQLite"
license = "LicenseRef-PolyForm-Noncommercial-1.0.0"
kanon_ci = true

[extra.headline_claim]
claim = "One local supervisor owns instrument access, admission, durable intent, execution, and reconciliation."
receipt = "docs/IMPLEMENTATION.md; no physical fixture is commissioned at initialization"

[extra.demo]
system = "cheirismos"
action = "sacrificial-fixture qualification"
target = "one target-specific profile and fault-matrix evidence"
shows = "The qualification boundary applied to one isolated fixture, including bounded refusal cases."
not_shows = "A qualified customer target, a recovery outcome, or universal physical-device support."
+++

## What it is

cheirismos gives agents typed operations over a device under test. It is designed for firmware recovery, board bring-up, hardware diagnosis, validation, and work where the device's own software may not run.

An authorized agent works only inside a target-specific delegation. A physical effect requires a commissioned profile, active grant, reviewed plan, durable journal admission, exclusive lease, and live interlocks. An interrupted effect remains unknown until fresh device evidence reconciles it.

## Current source

The public source defines a local supervisor that owns instrument access, grants, budgets, durable intent, execution, and reconciliation. CLI and MCP are local clients of that supervisor. They do not open the journal, artifact store, or instruments directly.

## What's open

cheirismos is in development. No physical fixture is commissioned at initialization, and software tests do not establish a safe physical procedure. Each target and instrument needs its own qualification evidence before a grant can authorize a physical effect.

## Where to look

- Repo: [cheirismos repository](https://github.com/forkwright/cheirismos)
- Current implementation and verified-state boundary: [`docs/IMPLEMENTATION.md`](https://github.com/forkwright/cheirismos/blob/main/docs/IMPLEMENTATION.md)
- Fixture and instrument qualification: [`docs/QUALIFICATION.md`](https://github.com/forkwright/cheirismos/blob/main/docs/QUALIFICATION.md)
- Public scope and limits: [`README.md`](https://github.com/forkwright/cheirismos/blob/main/README.md)
