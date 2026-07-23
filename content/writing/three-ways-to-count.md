+++
title = "Three ways to count the same thing"
description = "One number triangulated three ways, a SHA-bound local gate stamp followed by independent post-push CI, an audit checked against its tracker."
date = 2026-07-21

[extra]
components = "triangulation · unshared failure modes · system of record"
words = "~1120 words"
+++

A number in a README is a report about the day somebody counted. The system underneath keeps moving, and the sentence does not. Tools get deleted and the count survives them, modules merge and the count survives that too. Nobody lied. Someone counted once, wrote the number down, and the writing outlived its truth. People pay little for this, because people discount documentation on instinct. An autonomous agent reading a catalog to decide which tool to call extends no such discount - it takes the number literally, every time.

I maintained an MCP tool surface commercially - MCP is the protocol agents use to discover and call tools - inside an agent-infrastructure workspace whose catalog was load-bearing: agents planned real work against what it said. The surface grew the way tool surfaces grow: near-duplicate variants, split pairs that should have been one tool, a catalog trailing all of it. At its widest the live surface held 152 tools. A staged consolidation collapsed the duplicates, and the count settled at 137.

137 is the kind of number nobody should take from its author on faith, including the author. I state it without qualification anyway, because of how it is produced.

The first count reads the source. Every tool on the surface is declared by an attribute on its handler function. Grep the server source for that attribute. It returns 138 matches, and one of the 138 is a string literal quoting the attribute rather than declaring a tool. Excluded, the source declares 137. The false positive earns its place in the story: the first counting method misfired on its first use, and the real number came from inspecting the matches, not from trusting the total.

The second count reads the running process. The catalog is regenerated from the live daemon, not hand-maintained prose, and its meta block records how many tools the daemon was serving at generation time. 137.

The third count reads the artifact. Grep the regenerated catalog file itself and count the entries. 137.

| Count | What it reads | What would fool it |
|---|---|---|
| Attribute grep over the source | what the code declares | text shaped like a declaration (one was); a tool that fails registration at runtime |
| Meta field from the live daemon | what the process serves | a stale regeneration; a defect in the regeneration code itself |
| Entry grep over the catalog | what the artifact contains | format drift; a duplicated entry |

The right-hand column is the argument. The three methods hold no failure mode in common. A string literal cannot fool the daemon, a stale regeneration cannot fool the source grep, and drift in the artifact's format leaves the other two untouched. For all three to agree on a wrong number, three unrelated defects would have to err by the same amount, in the same direction, at the same time. The evidence for 137 is agreement between methods that cannot be wrong for the same reason.

The distrust behind all this counting was earned. The first time a drift audit ran against the same surface - earlier in its life, when it held 128 tools - 105 of the 128 carried names outside the ten-verb convention the surface was designed around. The convention was real, the tools were real, and the two had drifted four-fifths of the way apart while the prose stayed serene. From then on, any claim the surface's documentation made about the surface was treated as unverified until re-derived from the surface itself: the catalog now regenerates from the running daemon instead of being hand-maintained, and every number it reports gets checked by triangulation before anyone trusts it.

---

The same rule holds in a second codebase that shares no code and no domain with the first. kanon - the name is Greek for a measuring rod - runs the git forge, the lint engine, and the audit machinery for my own repositories, where AI agents work alongside me daily.

When kanon's local gate stamps a commit, the trailer records the installed Kanon version, the stages that ran, and the exact Git tree SHA it checked. The SHA binding is landed: reusing that local trailer after changing the tree fails the local clean-tree check. The trailer is still plain text, however, and any process that can write a commit message can forge its shape.

In the source inspected on 2026-07-22, the forge does not turn that trailer into synchronous push rejection. Its post-receive hook runs after the ref has moved, posts the pushed SHA to the server, and enqueues CI keyed to that revision, and the resulting run reports independently on the pushed artifact. That is useful verification, but it cannot retroactively make a forged trailer prevent the push that carried it. Trailer rejection at the receive boundary is accepted design work, not a property of the post-receive mechanism.

kanon's audit engine fans finder agents out over a codebase, then verifies, deduplicates, and files what survives. The invariant list in its decision record includes this one: after every batch, the orchestrator queries the issue tracker and reconciles the filed count against what the agents reported. The self-report is never accepted, only checked. The engine's runbook carries the mirror rule: a finding that an agent's reply omits is kept and flagged, never silently dropped, and only an explicit mechanical verdict - confirmed unreal, or a high-confidence duplicate - removes anything from the run. Every run closes with a disposition report in which each candidate is accounted for: filed, dropped with a stated reason, or flagged for review.

The rule reads as paranoia until someone watches agents work. An agent that filed four findings and reports five is not lying in any human sense: the report of the work is generated by the same process that generated the work, and inherits that process's blind spots. Querying the tracker instead of trusting the self-report is what catches the miscount.

---

In every case the claim came from the graded party - the catalog speaking for the surface it documents, the trailer vouching for the commit that carries it, the reporter closing its own batch. And in every case a verifier was already running, one query away, with no stake in the answer.
