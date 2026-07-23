#set document(
  title: "Cody Kickertz — Résumé",
  author: "Cody Kickertz",
  date: none,
)
#set page(
  paper: "us-letter",
  margin: (x: 0.58in, y: 0.48in),
  numbering: none,
)
#set text(font: "Nimbus Sans", size: 8.55pt, fill: rgb("241d18"))
#set par(justify: false, leading: 0.43em)
#set list(marker: [•], indent: 0.9em, body-indent: 0.45em, spacing: 0.22em)

#let rust = rgb("9e4a1e")
#let muted = rgb("665c54")

#let section(title) = {
  v(0.58em)
  line(length: 100%, stroke: 0.55pt + rust)
  v(0.18em)
  text(font: "Nimbus Sans", size: 9.2pt, weight: "bold", fill: rust, tracking: 0.055em, title)
  v(0.18em)
}

#let role(name, dates, subtitle: none) = {
  grid(
    columns: (1fr, auto),
    column-gutter: 0.6em,
    [#text(weight: "bold", name)#if subtitle != none { [ · #subtitle] }],
    text(fill: muted, dates),
  )
}

#let system(name, body) = grid(
  columns: (15%, 1fr),
  column-gutter: 0.65em,
  text(weight: "bold", fill: rust, name),
  body,
)

#align(center)[
  #text(size: 18pt, weight: "bold", tracking: 0.07em)[CODY KICKERTZ]
  #v(0.12em)
  #text(size: 10.3pt, weight: "semibold")[AI Systems Architect · Platform & Infrastructure]
  #v(0.12em)
  #text(fill: muted)[Rust · agent runtimes · governed AI infrastructure · distributed systems]
  #v(0.18em)
  #link("mailto:Cody.Kickertz@pm.me")[Cody.Kickertz\@pm.me] · // kanon:ignore OIKOS/private-content -- intentionally public professional contact preserved from the prior resume
  #link("https://ardent.tools")[ardent.tools] ·
  #link("https://github.com/forkwright")[github.com/forkwright] · Austin, TX
]

#section("SELECTED SYSTEMS · PUBLIC REPOSITORIES UNLESS MARKED PRIVATE")

#system("Aletheia", [Self-hosted multi-agent AI runtime with embedded Datalog and HNSW state over a knowledge graph; eleven-factor recall; per-tool Landlock, seccomp, and network-namespace controls; multi-provider LLM layer with circuit breaking and loop detection. Ships as one binary with embedded state; inference uses a configured LLM provider, and optional tools or messaging channels can open network paths.])
#v(0.28em)
#system("Kanon", [#text(weight: "bold")[Private case study.] Standards-and-dispatch control plane for a multi-repository fleet: standards-as-code linting, Rust-analyzer HIR checks, MCP tooling, git forge, CI, and a compare-and-swap work queue. Public receipt: six featured public repositories carry repository-owned `.kanon-ci.toml`; enforcement scope differs by repository.])
#v(0.28em)
#system("Logismos", [GPU inference stack for AMD RDNA3 in progress: hand-written HIP FFI and WMMA kernels, a custom GGUF loader, and attention from first principles. Verified end to end on CPU; GPU cutover remains scoped and blocked on hardware access.])
#v(0.28em)
#system("Hamma", [Clean-room Rust implementation of a Tailscale-compatible control protocol—not a translation of the Go source. Noise IK handshake, control-plane wire types, TCP/TLS registration, and map streaming have landed with byte-level tests; the BoringTun-backed WireGuard data plane is planned.])
#v(0.28em)
#system("Thumos", [From-scratch bare-metal OS for an Armv7 smartphone target. Own MMU, log-structured filesystem, Ed25519 measured boot, and Signal protocol implementation; treats the cellular baseband as an untrusted peripheral behind a driver boundary. Cross-compiled and QEMU-tested.])
#v(0.28em)
#system("Harmonia", [Self-hosted media platform: custom QUIC renderer protocol with NTP-style clock sync, lock-free audio ring buffer, biquad DSP pipeline, and a headless Raspberry Pi renderer through a NixOS AArch64 cross-build.])

#section("EXPERIENCE")

#role("Summus Global", "2023–Present", subtitle: "Data Scientist & AI Systems Architect")

- Architected an agent-native internal analytics platform in Rust: a governed MCP tool server with 137 tools over the data warehouse, protected by SQL validation, SELECT-only database policy, and a hard block on raw-CLI writes against production PHI.
- Built a standards-as-code governance layer with 284 machine-enforced rules across 13 registries, wired to commit-time gates and a promotion loop that turns observed tool use into reviewed, durable infrastructure.
- Designed a medical-code taxonomy engine spanning 301,000 ICD-10, CPT, HCPCS, and SNOMED codes in a four-level, 7,771-node hierarchy, projected in 12 seconds; implemented a multi-task LoRA fine-tune and verified its LoRA-to-Candle conversion without application-code changes.
- Replaced a 40-cell Hex/Python ROI-scoring notebook with a production Rust engine at exact parity on a \$4.18M validation client; identified three compounding legacy scoring defects and rebased a flagship analysis onto a third-party-validated basis.
- Added a claims-manifest gate pairing each client-facing figure with a runnable, tolerance-bound SQL check before a report can ship across 30+ ROI engagements.

#role("Summus Global", "2023–2025", subtitle: "Database, Data & Business Intelligence Analyst")

- Designed an AWS Redshift dimensional model using star/snowflake patterns, CTEs, and window functions, powering eight dashboards and 40+ ROI analyses across the business.
- Built a React/FastAPI medical-taxonomy system with 50+ endpoints and PostgreSQL, Redis, Qdrant, and Elasticsearch, serving 192,000 hierarchical records with semantic search.
- Built physician deduplication with fuzzy matching and NPI reconciliation, raising NPI coverage from 33% to 92% across 1,200+ profiles and unblocking three dependent product features.

#pagebreak()

#align(center)[
  #text(size: 12pt, weight: "bold", tracking: 0.06em)[CODY KICKERTZ]
  #h(0.7em)#text(fill: muted)[ardent.tools · Cody.Kickertz\@pm.me]
]

#section("LEADERSHIP & EARLIER EXPERIENCE")

#role("United States Marine Corps — Captain", "2018–2023", subtitle: "Camp Lejeune, NC")

#text(weight: "bold")[Assistant Disbursing Officer · Dec 2022–May 2023]

- Helped lead a disbursing office of 157 Marines and 12 civilians across seven finance functions.
- Reengineered core disbursing processes: 16% faster processing, 14% accuracy gain, roughly 375 hours returned annually, and a 3,000+ claim backlog eliminated across \$45M+ in military pay and travel claims.

#text(weight: "bold")[Disbursing Officer, 22d Marine Expeditionary Unit · Aug 2021–Dec 2022]

- Ran fiscal operations for a 3,000-person MEU through a seven-month deployment aboard three naval vessels.
- Managed a \$350,000 deployed cash budget with zero discrepancies; consolidated three accounting systems into one, later adopted by East Coast MEU deployments.

#text(weight: "bold")[Travel Section Officer-in-Charge · Dec 2018–Aug 2021]

- Led a 62-person travel-claims section supporting 60,000+ service members, civilians, and dependents across the eastern United States and Europe.
- Reduced claim backlogs 30% through workload triage, process redesign, and production tracking.

#v(0.35em)
#role("Clarkson Aerospace Corp", "2015–2018", subtitle: "Cyber Security Research Intern · Houston, TX")

- Built a predictive intrusion-detection system for the Air Force Research Laboratory using PCA, k-medoids clustering, and SVM classification in R; reached 98% accuracy on a 125,000-observation network-traffic dataset.
- Selected to present the research at Pentagon Lab Day and the Georgia Institute of Technology.

#section("TECHNICAL")

#grid(
  columns: (16%, 1fr),
  row-gutter: 0.34em,
  column-gutter: 0.6em,
  text(weight: "bold", fill: rust)[Languages], [Rust (primary), Python, SQL, TypeScript, R, Bash/Fish, Nix, Typst],
  text(weight: "bold", fill: rust)[Agent / AI], [MCP tool servers, agent orchestration and dispatch, standards-as-code governance, RAG, embeddings with Candle and MedEmbed, LoRA/MNRL/Matryoshka fine-tuning, clinical NLP],
  text(weight: "bold", fill: rust)[Systems], [Tokio async, fjall/LSM, QUIC/Quinn, Landlock/seccomp, WireGuard/Noise, no_std/embedded, HIP/GPU kernels],
  text(weight: "bold", fill: rust)[Data], [AWS Redshift, Polars, SQLite, dimensional modeling, ETL pipelines, Hex in HIPAA environments],
  text(weight: "bold", fill: rust)[Infrastructure], [Podman, systemd, Tailscale, NixOS, GitHub Actions, restic, nftables],
)

#section("EDUCATION")

#role("The University of Texas at Austin — McCombs School of Business", "May 2026", subtitle: "MBA")
#v(0.18em)
#role("University of Houston — College of Technology", "", subtitle: "BS, Computer Information Systems")
