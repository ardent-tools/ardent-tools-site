+++
title = "Ardent Politeia"
description = "A development-stage institutional control plane for human and machine work. Its planned first package learns approved knowledge before specific use; no deployment proof exists."
weight = 8
template = "system.html"

[extra]
gloss = "πολιτεία - an institutional order"
badge = "DEVELOPMENT · COMMISSIONING PACKAGE OPEN"
repo = "https://github.com/ardent-tools/politeia"
stack = "Rust · JSON Schema · TLA+"
license = "MPL-2.0"
kanon_ci = true

[extra.headline_claim]
claim = "The planned commissioning package learns approved institutional knowledge before a specific operational use."
receipt = "ADR 0021 commissioning contract; no package proof has been published"

[extra.demo]
system = "Ardent Politeia"
action = "full public-source commissioning package"
target = "two separate synthetic institutions for software development and analytics"
shows = "The planned learning, approval, governed-work, correction, generation, handoff, revocation, and replacement-maintainer path."
not_shows = "A client deployment, a feature-complete product, or production assurance for broader adapters, transports, or topologies."
+++

## What it is

Ardent Politeia is intended to give an institution an explicit, typed, evidence-bearing model for human and machine work. Its planned first package can establish approved institutional knowledge through authorized discovery before a specific operational use is selected. Each task context and protected effect remains explicitly scoped; learning cannot authenticate its own evidence, approve its own proposals, or enlarge authority.

## Current source

The public repository remains a starter architecture, not a feature-complete product. Its commissioning direction is being refined into the full commissioning contract in ADR 0021. That planned loop is observation, candidate claims and conflicts, authenticated approval, authorized context and discovery, governed work, feedback, proposed corrections, and approved changes. The contract has no runtime package receipt yet.

## What's open

The full commissioning package remains unproved. It must demonstrate installation; PostgreSQL persistence; a reusable Rust semantic API; an administrative CLI and local authenticated daemon; signed immutable generation verification with atomic activation and rollback; operation after commissioner revocation; and replacement-maintainer recommissioning. Its proof uses two separate synthetic institutions for software development and analytics, neither a client deployment. The site has no cast, release, deployment, or package receipt for Ardent Politeia, and makes no assurance claim for broader adapters, transports, or deployment topologies.

## Where to look

- Repo: [github.com/ardent-tools/politeia](https://github.com/ardent-tools/politeia)
- Product scope and starter-architecture boundary: [`README.md`](https://github.com/ardent-tools/politeia/blob/main/README.md)
- Current commissioning and handoff baseline: [`docs/18-FIRST_VERTICAL_SLICE.md`](https://github.com/ardent-tools/politeia/blob/main/docs/18-FIRST_VERTICAL_SLICE.md) and [`docs/20-ENGINEERING_HANDOFF.md`](https://github.com/ardent-tools/politeia/blob/main/docs/20-ENGINEERING_HANDOFF.md)
- Planned full commissioning contract: ADR 0021, *Institutional learning and complete commissioning*, once it lands in the public repository.
