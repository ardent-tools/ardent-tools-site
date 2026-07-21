+++
title = "The hardest honest rung"
description = "Five rungs a rule can live on, from merge gate to one-off prompt, and the mirror-image failures: prose that reads enforced and rots, gates that certify a proxy and lie."
date = 2026-07-20

[extra]
components = "hardness ladder · demotion law · proxy gates"
words = "~1600 words"
+++

A lint rule that blocks a merge cannot rot. A paragraph in a style guide can do little else. Every rule an engineering organization writes down lives somewhere between those two poles, and the standard advice about placement (automate more, shift left, put it in CI) describes travel in one direction only.

The failure that advice targets is real. An enforceable invariant left in prose reads as if it were enforced, and it is not: nobody re-reads the document, exceptions accumulate, and within months it describes a codebase that no longer exists.

The mirror-image failure rarely gets named. Take a genuine judgment call, the kind a reviewer makes: are these acceptance criteria complete; is this paragraph motivated or redundant. Force it into a mechanical gate and the gate will check something — a word list, a line count, the presence of a heading — and then report the judgment as verified. The prose rule merely rots. The gate lies, with a green checkmark, on every run.

---

The repositories I maintain are worked on by AI agents as much as by me, which multiplies the places a rule can live. Prose-or-CI stretches into a five-rung ladder, codified in the standards library of kanon, the system that runs the forge, the lint engine, and the audit machinery for my repositories. The placement document is named TEKHNE.md, after tekhne, the Greek word for craft: the knowledge of how a thing is well made. Its spine is one table.

| Rung | Home | Precondition | Test |
|---|---|---|---|
| 5 | hook / gate | mechanical invariant, enumerable failures, catastrophic when wrong | a known-bad fixture is blocked |
| 4 | tool | repeatable multi-step procedure, stable input→output contract | call counts and error rates |
| 3 | durable context | judgment or doctrine that resists deterministic encoding | a fresh reader reconstructs the same judgments |
| 2 | thin config | ephemeral values for one task: which issues, which crate, which lanes | a golden render |
| 1 | one-off prompt | truly one-off, never recurs | none — the last resort |

The placement rule is a single sentence: every behavior settles at the hardest rung whose precondition it meets. The preconditions do the work. A rule earns the gate rung only when it is mechanical and its failure modes can be enumerated; doctrine that resists deterministic encoding stops at the context rung no matter how much anyone cares about it. Importance never places a behavior. Checkability does.

The test column is the ladder's check on itself: every rung above the bottom carries a way to catch its own failure. The bottom rung has no test. That is not a gap in the table; it is the reason a one-off prompt is the last resort.

---

The first law governs behaviors sitting too soft. A behavior on a softer rung that meets a harder rung's precondition is a defect — the demotion law: move it to the harder rung. Once it lands there, the prose that used to state it is dead weight, and the law says to delete it, because a hook-enforced rule restated in a document is a second copy of a fact that now has a canonical home, and second copies drift. The consequence runs against instinct: the documentation shrinks as the system hardens.

Most rules split instead of moving whole. One writing standard in my fleet flags hedge-word clusters: two or more hedge words within ten words of each other. The enumerable half of that rule, the word list itself, meets a harder rung's precondition, so the list compiled into a lint rule; the linter now names the words and the line. What stayed behind in the standards document is the residue no regex can hold: whether a sentence hedges structurally, parking uncertainty beside a claim without using any listed word. One rule, two rungs, each honest about what it can catch.

---

The second law is the stop. A behavior a gate can only check a proxy for must not be pushed onto a hook, because the proxy misfires on exactly the edge cases that matter: whether a change's stated scope matches its blast radius has cheap proxies, and every one is wrong precisely where the question gets hard. Forcing the judgment down builds a gate that certifies the proxy while claiming to certify the property, which is worse than no gate. No gate leaves the question visibly open. The proxy gate closes it falsely.

My own system supplied the cautionary instance. An assessment of kanon's quality machinery found a cluster of writing rules — about forty word-bans plus filler and minimizer checks — attacking vocabulary as a stand-in for the quality property itself, with the teeth misplaced around them: about four rules blocked merges while more than a hundred warned into logs nobody read. The correction was not more rules. Every rule is now tagged substance or proxy, only substance rules can block a merge, and a check that cannot be made substance-faithful is classified advisory and may never be an error. Naming the proxy as a proxy is itself the honest placement.

The two laws describe one defect seen from opposite directions. The under-hardened rule reads enforced and is not. The over-hardened gate reads enforced and lies. Both substitute a proxy for the property they claim, and the placement that avoids both is the discipline's whole content: the hardest rung at which the behavior stays both enforced and true. The hardest honest rung.

---

Placement needs an admission test, and the one kanon's decision records use is reflexive: no lint rule and no design document is admitted unless passing it means the property is present, not a proxy satisfied. The record that established the bar applied it to its own text and struck an unfalsifiable superlative about itself from an earlier draft. The decisive question at admission never changes: does the thing exhibit the property it claims, or assert it? A vault that stores plaintext asserts. The question sounds philosophical until it catches something running.

It caught the judge. kanon includes a judge: the component that renders verdicts on semantic claims — does this audit finding hold, is this metric honest, is this recalled fact still true. Held against the admission bar, the shipped judge failed.

The decision record states it without cushioning: the current judge is a label; it returns a typed verdict, but passing does not mean the property "grounded, calibrated judgment" is present. Two absences made it one. No verdict was bound to its evidence: the judge model was handed a context window someone else assembled, so a confident verdict could rest on the wrong lines, and a confident wrong verdict is worse than none, because it launders error into the record. And no verdict was bound to calibration; nothing failed when a change silently flipped a case with a known correct answer.

The redesign is the ladder applied to the failure. Everything enumerable was demoted to machinery. A grounding step now issues the evidence together with a token, the SHA-256 of the exact evidence bytes consumed, and a verdict that does not echo a live token is rejected; a judge that finds the issued evidence too narrow re-calls the grounder for a wider scope instead of reaching around it. Calibration became committed case files per claim kind, ten cases minimum, inverted-claim controls included, with a lint rule at error severity, `WORKFLOW/judge-uncalibrated`, that fires whenever a judge-affecting path changes without a fresh replay of the frozen cases.

The gate leg stays deterministic: it fails on a flipped known case, never on a live model call. The verdict itself, the one genuinely non-mechanical step, remains a judgment. The ladder hardened everything around it.

---

One class of behavior overrides both laws. "Is this operation safe to run right now" is a judgment call, and the second law would place judgment in context. For irreversible operations — a firmware write, a force-push, a release merge, a mutation of branch protection — the ladder refuses its own logic: the limits sit at the gate rung permanently, as hard policy, even though the gates holding them are blunt and over-block. Everywhere else, placement follows checkability; here it follows what a single wrong pass costs. A discipline built on demotion keeps one class it refuses to reason about, because a system clever enough to argue its way past its own safety floor eventually will.

---

The ladder's least obvious consequence is about tone. Durable context is written calm and explicit, with the motivation stated, not in imperative capitals. A context document that shouts (`CRITICAL`, `MUST`, `NEVER`) degrades the agent reading it: the model reads volume as stakes and escalates, asking for confirmation it does not need, fanning out subagents where one would do. That is observation from operating these systems daily, not received prompt-engineering wisdom.

The shouting is also a diagnostic. An invariant that seems to deserve capital letters is one somebody believes must never fail, and that belief is the gate rung's precondition knocking. A gate does not read tone. Once the invariant is mechanical the register question dissolves, and what remains in prose can afford to explain itself quietly, because nothing rides on whether prose is obeyed; everything that could ride on obedience has been moved somewhere obedience is not optional. The loudest register on the softest rung, the shouted one-off prompt, is the worst case the ladder names: soft and mistuned at once. Calming the register and hardening the rung are the same move. Certainty lives in the mechanism, not the shouting.
