+++
title = "FAQ"
description = "Direct answers to the questions this site's format tends to raise: private repos, maturity labels, location, availability, why so many systems, and agent readability."
template = "faq.html"

[[extra.questions]]
q = "Why are some repos private?"
a = "Two different reasons. kanon is private by choice because it is not yet hardened for public traffic. The six featured public system repositories carry .kanon-ci.toml, but each repository declares its own enforcement scope. [Its case-study page](/systems/kanon/) makes that narrower relationship inspectable without exposing the source. Systems I built in employment belong to that employer and are described only as professional experience, never presented as portfolio."
anchor = "private-repos"

[[extra.questions]]
q = "What does a label like 'pre-alpha' or 'Phase 4 blocked on hardware' actually mean?"
a = "It is a derived summary of pinned repository evidence, not a verbatim status-line quote. Each label is bounded by the source, revision, and open limits published on that system page - it is never rounded up."
anchor = "labeling"

[[extra.questions]]
q = "Are you open to relocation or remote work?"
a = "Remote-first, based in Austin, Texas. Happy to talk specifics directly."
anchor = "remote"

[[extra.questions]]
q = "What's the comp range or availability?"
a = "Depends on the role and scope. Short version, as of 2026-07: in a W2 search alongside a part-time consulting engagement through October 2026. Ask directly at [/contact/](/contact/) and I'll give a straight answer."
anchor = "availability"

[[extra.questions]]
q = "Why so many independent systems instead of one thing?"
a = "Because the thing being demonstrated is a systems-engineering practice, not a single startup pitch. Six featured public system repositories carry repository-owned Kanon configuration, with enforcement scoped independently rather than claimed as uniform. The catalog at [/systems/](/systems/) keeps each system's maturity and limits visible."
anchor = "why-many-systems"

[[extra.questions]]
q = "Is the site readable by an AI agent?"
a = "Yes, for live retrieval on a visitor's behalf. [llms.txt](/llms.txt) indexes the structured surfaces - the [machine-readable systems catalog](/systems.json), the [career-claims receipt](/career-claims.json), and this repository's own AGENTS.md - all derived from the same frontmatter the human pages render from. The [AI use policy](https://github.com/ardent-tools/ardent-tools-site/blob/main/AI-USE-POLICY.md) draws the line at bulk collection into a training corpus, which stays prohibited without written consent."
anchor = "agent-readable"
+++

Anything not covered here, ask directly: [cody@ardent.tools](mailto:cody@ardent.tools).
