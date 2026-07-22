+++
title = "Systems"
description = "Seven systems, the libraries underneath them, and what's on the drawing board: seventeen public repositories and one private tool with a public track record."
sort_by = "weight"
template = "systems.html"

[extra]
[[extra.ledger]]
name = "theatron"
gloss = "θέατρον — the seeing-place"
one_liner = "Desktop UI primitives for the fleet: Dioxus/Blitz components, design tokens, markdown rendering, HTTP/SSE, OS integration."
badge = "v1.4.0 · API FROZEN"
license = "MIT OR Apache-2.0"
repo = "https://github.com/forkwright/theatron"
group = "libraries"

[[extra.ledger]]
name = "heurema"
gloss = "εὕρημα — a thing found"
one_liner = "Contracts for vector search, full-text search, persistence, and rank fusion. Reciprocal-rank fusion is implemented; HNSW and BM25 land by extraction from their in-app implementations."
badge = "IMPLEMENTED: RRF · INTERFACES: HNSW, BM25"
license = "AGPL-3.0"
repo = "https://github.com/forkwright/heurema"
group = "libraries"

[[extra.ledger]]
name = "sphragis"
gloss = "σφραγίς — a seal"
one_liner = "Post-quantum hybrid sealing: an X-Wing KEM (X25519 + ML-KEM-768) with a ChaCha20-Poly1305 envelope, behind an explicit feature flag."
badge = "UNAUDITED PREVIEW"
license = "AGPL-3.0"
repo = "https://github.com/forkwright/sphragis"
group = "libraries"

[[extra.ledger]]
name = "koinon"
gloss = "κοινόν — that which is shared"
one_liner = "Fleet-common Rust scaffolding: tracing init, typed errors, config loading, a CLI prelude."
badge = "v0.1.1"
license = "Apache-2.0"
repo = "https://github.com/forkwright/koinon"
group = "libraries"

[[extra.ledger]]
name = "epitelesis"
gloss = "ἐπιτέλεσις — executing-to-completion"
one_liner = "A typed subprocess wrapper over std and tokio: timeouts as contract, captured output, structured errors."
badge = "v0.2.0"
license = "Apache-2.0 OR MIT"
repo = "https://github.com/forkwright/epitelesis"
group = "libraries"

[[extra.ledger]]
name = "zetesis"
gloss = "ζήτησις — systematic inquiry"
one_liner = "Budget, cost, citation, and query contracts for agent research pipelines, with a fixture-driven deep-research loop."
badge = "PHASE 1 SCAFFOLD"
license = "AGPL-3.0"
repo = "https://github.com/forkwright/zetesis"
group = "libraries"

[[extra.ledger]]
name = "typikon"
gloss = "τυπικόν — the book of order"
one_liner = "The Zola theme, frontmatter schemas, and CI gate bundle this site itself runs on: CSP enforcement, link checking, accessibility, smoke tests."
badge = "PINNED BY COMMIT · NO RELEASE TAG"
license = "AGPL-3.0"
repo = "https://github.com/forkwright/typikon"
group = "web"

[[extra.ledger]]
name = "epistole"
gloss = "ἐπιστολή — a letter"
one_liner = "Subscriber lifecycle and archive flows over an embedded store; SMTP delivery is the next phase."
badge = "PHASE 1 · SMTP PENDING"
license = "AGPL-3.0"
repo = "https://github.com/forkwright/epistole"
group = "web"

[[extra.ledger]]
name = "pinax"
gloss = "πίναξ — the tablet, the register"
one_liner = "A relational storage engine designed from scratch in Rust: multi-writer MVCC, per-page encryption, a causal changelog as a storage primitive. Design documents only; implementation not started."
badge = "DESIGN PHASE"
license = "PolyForm Shield 1.0.0"
repo = "https://github.com/forkwright/pinax"
group = "in-design"

[[extra.ledger]]
name = "mneme"
gloss = "μνήμη — memory as faculty"
one_liner = "A Datalog engine for facts, rules, and inference: content-addressed facts, supersede-based retraction, incrementally maintained views. Design documents only; implementation not started."
badge = "DESIGN PHASE"
license = "PolyForm Shield 1.0.0"
repo = "https://github.com/forkwright/mneme"
group = "in-design"

[[extra.ledger]]
name = "dioptron"
gloss = "δίοπτρον — the instrument through which one sees"
one_liner = "A specification for a web runtime where operator and agents share one capability surface: browsing, ingesting, querying, acting. Design documents only; implementation not started."
badge = "DESIGN PHASE"
license = "AGPL-3.0"
repo = "https://github.com/forkwright/dioptron"
group = "in-design"
+++

Seven systems, the libraries underneath them, and what's on the drawing board: seventeen public repositories and one private tool with a public track record. Order within a group is each page's own weight.
