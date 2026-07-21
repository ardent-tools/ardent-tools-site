+++
title = "nosologia"
description = "An embedding-canonical medical-code taxonomy engine, solo-built in Rust in an eight-day sprint: 301K codes as a semantic space, projected into navigable hierarchies."
weight = 5
template = "system.html"

[extra]
badge = "PRIVATE · CASE STUDY"
private = true
stack = "Rust · single static binary · local BERT inference (candle)"
svg_diagram = "img/systems/nosologia-arch.svg"
svg_diagram_alt = "nosologia pipeline: raw medical code sources feed a fine-tuned embedding model, which feeds bisecting k-means projection into a navigable hierarchy and exportable formats"
svg_diagram_caption = "No demo. This system is employer property; the patterns are the transferable part."

[extra.headline_claim]
claim = "97.5% cluster purity, fine-tuned from scratch"
receipt = "v3 eval, corroborated across three independent sources · 2026-03-24"
+++

## What it is

nosologia is an embedding-canonical medical-code taxonomy engine: it manages the full universe of medical classification codes (ICD-10-CM, ICD-10-PCS, CPT, HCPCS, SNOMED, and modifiers) as a semantic embedding space, then projects that space into navigable hierarchies, searchable indexes, and exportable formats. The design thesis, stated in the project's own planning docs: codes as embeddings, trees as projections — the canonical representation is semantic, not a hand-built tree. I built it solo, in Rust, in about eight calendar days of intensive work following a longer research and planning stretch.

Like ergon-tools, this is employer property. The write-up below stays inside what's already cleared for public description — no internal system names, no schema names, no dollar figures.

## Decisions and trade-offs

### Semantic representation instead of a hand-maintained tree

The system it replaced was a fixed, hand-built taxonomy tree that had accumulated real structural debt over time: categories that had grown lopsided, codes filed in catch-all buckets, gaps nobody had caught. Rather than patch that tree, nosologia fine-tunes an embedding model over the full code space and derives every hierarchy from the embeddings by projection. The trade-off: a fixed tree is easier to reason about by inspection; a projected one is regenerable — adding a year's worth of new codes means adding vectors, not manually deciding where each one goes.

### Starting the production model fresh, not iterating on a broken foundation

Two earlier model generations (triplet-loss training, then the same architecture with more data) produced only marginal or broken results. Rather than keep tuning that lineage, the production model started over from a stock pretrained checkpoint with a different loss function entirely. The reasoning, stated directly during the build: you can't fix a warped foundation by building on it. Continuing to iterate on the first two generations would have been the easier-looking path in the moment; it was the one rejected.

### A single static binary, no external services

Like the other systems on this site, nosologia has no Postgres, no Redis, no Docker Compose. Vectors live in `fjall`, a pure-Rust LSM store, indexed with `hnsw_rs` for nearest-neighbor search; `polars` and `rayon` run the bisecting k-means that turns the embedding space into a navigable hierarchy; `rusqlite`/FTS5 carries text search. One binary, modeled explicitly on the same no-external-dependency deployment pattern used elsewhere in this practice. The trade-off is the same one it always is: an external vector database or search service would have offered more off-the-shelf tooling; the single-binary model wins because it's what keeps the deployment story actually simple rather than simple in the README.

## What's solid / what's open

**Solid:** the full 301K-code pipeline (ingestion, embedding, and dual hierarchical projection) running end to end, QA-clean. A self-built static-analysis audit tool was run against the finished pipeline and every finding it surfaced, including one SQL-injection-shaped defect, was fixed in a single pass.

**Open:** internal roadmap and integration specifics for the system this replaces stay confidential — that boundary is deliberate, not a maturity gap this page is hiding.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Method | Where to check |
|---|---|---|
| 301,000 medical codes ingested, 220,945 unique after dedup | direct row count against the built index | private repo; artifact available on request |
| 97.5% cluster purity, 85% retrieval recovery | v3 model eval, corroborated across three independent sources (session notes, memory record, an independent cross-repo citation) | private repo; artifact available on request |
| 1,352,223 training pairs from 28 sources | session notes + memory record, cross-corroborated | private repo; artifact available on request |
| Full 301K-code embedding: 43s on GPU; full projection: 12s; SQLite load: 2.8s | directly measured against a committed pipeline run | private repo; artifact available on request |
| Working engine built in an ~8-calendar-day sprint | dated commit history | private repo; artifact available on request |

</div>

## Where to look

- Repo: private, employer property — no public link
- What it's like to use: the architecture diagram above is the closest public artifact; ask directly for a redacted review pack
