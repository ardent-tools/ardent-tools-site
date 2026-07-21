+++
title = "Three ways to count the same thing"
description = "One number confirmed by three methods with no shared failure mode; a gate stamp the server recomputes before honoring; an audit run that checks agents against the tracker they filed into."
date = 2026-07-21

[extra]
components = "triangulation · unshared failure modes · system of record"
words = "~1120 words"
+++

A number in a README is a report about the day somebody counted. The system underneath keeps moving; the sentence does not. Tools get deleted and the count survives them; modules merge and the count survives that too. Nobody lied. Someone counted once, wrote the number down, and the writing outlived its truth. People pay little for this, because people discount documentation on instinct. An autonomous agent reading a catalog to decide which tool to call extends no such discount — it takes the number literally, every time.

I maintained an MCP tool surface commercially — MCP is the protocol agents use to discover and call tools — inside an agent-infrastructure workspace whose catalog was load-bearing: agents planned real work against what it said. The surface grew the way tool surfaces grow: near-duplicate variants, split pairs that should have been one tool, a catalog trailing all of it. At its widest the live surface held 152 tools. A staged consolidation collapsed the duplicates, and the count settled at 137.

137 is the kind of number nobody should take from its author on faith, including the author. I state it without qualification anyway, because of how it is produced.

The first count reads the source. Every tool on the surface is declared by an attribute on its handler function. Grep the server source for that attribute and you get 138 matches, and one of the 138 is a string literal quoting the attribute rather than declaring a tool. Excluded, the source declares 137. The false positive earns its place in the story: the first counting method misfired on its first use, and the real number came from inspecting the matches, not from trusting the total.

The second count reads the running process. The catalog is not hand-maintained prose; it is regenerated from the live daemon, and its meta block records how many tools the daemon was serving at generation time. 137.

The third count reads the artifact. Grep the regenerated catalog file itself and count the entries. 137.

| Count | What it reads | What would fool it |
|---|---|---|
| Attribute grep over the source | what the code declares | text shaped like a declaration (one was); a tool that fails registration at runtime |
| Meta field from the live daemon | what the process serves | a stale regeneration; a defect in the regeneration code itself |
| Entry grep over the catalog | what the artifact contains | format drift; a duplicated entry |

The right-hand column is the argument. The three methods hold no failure mode in common. A string literal cannot fool the daemon; a stale regeneration cannot fool the source grep; drift in the artifact's format leaves the other two untouched. For all three to agree on a wrong number, three unrelated defects would have to err by the same amount, in the same direction, at the same time. The evidence for 137 is agreement between methods that cannot be wrong for the same reason.

The distrust behind all this counting was earned. The first time a drift audit ran against the same surface — earlier in its life, when it held 128 tools — 105 of the 128 carried names outside the ten-verb convention the surface was designed around. The convention was real, the tools were real, and the two had drifted four-fifths of the way apart while the prose stayed serene. From then on, any claim the surface's documentation made about the surface was treated as unverified until re-derived from the surface itself: the catalog now regenerates from the running daemon instead of being hand-maintained, and every number it reports gets checked by triangulation before anyone trusts it.

---

The same rule holds in a second codebase that shares no code and no domain with the first. kanon — the name is Greek for a measuring rod — runs the git forge, the lint engine, and the audit machinery for my own repositories, where AI agents work alongside me daily.

A commit that passes kanon's local quality gate is stamped with a trailer in its message: `Gate-Passed: kanon 0.5.2 +ruleset:fleet-2026q2` — which binary validated it, under which version of the rule set, so that what was enforced stays reconstructible after the rules drift. The stamp is also plain text, and the decision record that introduced it names the exposure in its own consequences list: a push can carry the trailer without the gate ever having run. Anything that writes commit messages can write stamps. So the forge's post-receive hook recomputes the answer. It validates every trailer against the actual gate outcome, and a mismatched or forged stamp rejects the push. The trailer is a claim made by the party that wants the push accepted; the server re-derives the fact before honoring the claim.

kanon's audit engine fans finder agents out over a codebase, then verifies, deduplicates, and files what survives. The invariant list in its decision record includes this one: after every batch, the orchestrator queries the issue tracker and reconciles the filed count against what the agents reported. The self-report is never accepted, only checked. The engine's runbook carries the mirror rule: a finding that an agent's reply omits is kept and flagged, never silently dropped, and only an explicit mechanical verdict — confirmed unreal, or a high-confidence duplicate — removes anything from the run. Every run closes with a disposition report in which each candidate is accounted for: filed, dropped with a stated reason, or flagged for review.

The rule reads as paranoia until you watch agents work. An agent that filed four findings and reports five is not lying in any human sense: the report of the work is generated by the same process that generated the work, and inherits that process's blind spots. Querying the tracker instead of trusting the self-report is what catches the miscount.

---

In every case the claim came from the graded party — the catalog speaking for the surface it documents, the trailer vouching for the commit that carries it, the reporter closing its own batch. And in every case a verifier was already running, one query away, with no stake in the answer.
