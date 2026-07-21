+++
title = "ergon-tools"
description = "An agent-native Rust harness built for a healthcare-analytics team: a 10-crate workspace, a 137-tool MCP surface, and a governed standards layer over a regulated data warehouse."
weight = 4
template = "system.html"

[extra]
badge = "PRIVATE · CASE STUDY"
private = true
stack = "Rust · 10-crate workspace · governed MCP tool surface"
svg_diagram = "img/systems/ergon-tools-arch.svg"
svg_diagram_alt = "ergon-tools layered architecture: agent-first MCP surface over a standards-as-code layer over a defense-in-depth write-guard stack, feeding a deterministic self-improvement loop"
svg_diagram_caption = "No demo. This system is employer property; the patterns are the transferable part."

[extra.headline_claim]
claim = "137-tool MCP surface, triple-independently verified"
receipt = "source attribute count, the auto-regenerated tool catalog, and a catalog-entry grep all agree · measured 2026-07-17"
+++

## What it is

ergon-tools is an agent-native Rust harness I built for a healthcare-analytics team: a 10-crate workspace exposing a 137-tool MCP surface and a 47-subcommand CLI over a regulated data warehouse, with SQL write-guards, fail-closed data-hygiene enforcement, a machine-enforced standards registry, and a deterministic self-improvement loop that doesn't rely on an LLM grading its own work.

This system is employer property. No repository link exists on this page and none will — the write-up below stays entirely within what's already been cleared for public description; the warehouse schema, product names, and stakeholder names all stay out. What's public here is the shape of the engineering, not the domain it runs in.

## Decisions and trade-offs

### Deferred-schema tool loading instead of front-loading everything

A 137-tool MCP surface, loaded naively, means every agent turn pays the context cost of every tool's schema whether it uses it or not. Instead, tool discovery is gated — a `ToolSearch`-style pattern that only pulls a tool's schema into context when something actually needs it — enforced by a 10-verb naming canon and a drift-detecting audit gate. The audit gate wasn't decorative: at its first run it caught 105 of 128 tools sitting on non-canon verbs, which is real evidence the discipline was needed, not just a nice idea.

### Three write-guard layers, and an explicit decision not to add a fourth

Writes into a regulated data warehouse behind an LLM agent get three independent layers of protection: an infra-policy layer (read-only at the platform level), an application-level validator, and a raw-CLI-grep layer — each one catching what the layer below it can't see. A fourth layer was considered and explicitly rejected once an existing compliance boundary (already in place for unrelated reasons) was confirmed to cover that specific residual risk. Building the fourth layer anyway would have been easy to justify on "more guardrails is always safer" grounds; the actual decision was to check whether it was load-bearing first, and skip it once the answer was no.

### A self-improvement loop that measures instead of promoting on faith

Runbooks (the system's SME-encoded execution recipes) track their own per-phase pass/fail history, flag underperformance automatically, and can auto-apply a capped number of additive refinements — but only after an empirical before/after measurement, not because a refinement looked reasonable. The system's own history records a documented self-critique from an earlier phase: a refinement got promoted on the strength of its rationale alone, without a measured comparison, and a later phase closed that gap by adding the measurement step this phase now enforces. That kind of "we did it wrong, here's the fix" is left in the record, not edited out.

## What's solid / what's open

**Solid:** the full write-guard stack described above, in production against a live regulated warehouse; the deferred-schema MCP tool surface at 137 tools; the standards registry with a verified zero-override track record; a runbook self-improvement loop with real pass/fail history behind it; a derive-over-declare pass that converted eight hand-maintained config/catalog registries into artifacts derived on read from their true source, which immediately surfaced real drift the hand-maintained versions had been silently carrying.

**Open:** everything specific to the employer's data domain, product names, and stakeholder relationships stays confidential by design — that's not a maturity gap, it's the actual boundary of what this page can say.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Method | Where to check |
|---|---|---|
| 10-crate Rust workspace | crate count in `Cargo.toml`, 486 source files (`fd -e rs`) | private repo; artifact available on request |
| 145,038 lines Rust (code-only), ~186K including embedded doc comments | `tokei` Code column, cross-checked by two independent measurement passes · 2026-07-17 | private repo; artifact available on request |
| 2,885 test functions | `rg -c '#\[(tokio::)?test'` (2,797 plain + 88 async) · 2026-07-17 | private repo; artifact available on request |
| 137-tool MCP surface | triple-confirmed: source attribute count, the auto-regenerated tool catalog (sourced from the live daemon), and a catalog-entry grep, all agreeing | private repo; artifact available on request |
| 284 enforced rules across 13 machine-readable registries | `rg -c '^\[\[rule\]\]'` summed across registry files · 2026-07-17 | private repo; artifact available on request |

</div>

Where a stale or inflated figure exists elsewhere (an earlier internal deck cited 145 tools and 12 crates), this table uses the directly re-measured number, not the deck's.

## Where to look

- Repo: private, employer property — no public link
- What it's like to use: the architecture diagram above is the closest public artifact; ask directly for a redacted review pack
