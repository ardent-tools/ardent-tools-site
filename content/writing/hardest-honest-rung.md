+++
title = "The hardest honest rung"
description = "Five rungs a rule can live on, from merge gate to one-off prompt, and the mirror-image failures: prose that reads enforced and rots, gates that certify a proxy and lie."
date = 2026-07-20

[extra]
tier = "research"
components = "hardness ladder · demotion law · proxy gates"
words = "~1600 words"
+++

A lint rule that blocks a merge cannot rot. A paragraph in a style guide can do little else. Every rule an engineering organization writes down lives somewhere between those two poles, and the standard advice about placement (automate more, shift left, put it in CI) describes travel in one direction only.

The failure that advice targets is real. An enforceable invariant left in prose reads as if it were enforced, and it is not - nobody re-reads the document, exceptions accumulate, and within months it describes a codebase that no longer exists.

The mirror-image failure rarely gets named. Take a genuine judgment call, the kind a reviewer makes - are these acceptance criteria complete, is this paragraph motivated or redundant. Force it into a mechanical gate and the gate will check something - a word list, a line count, the presence of a heading - and then report the judgment as verified, a green checkmark on every run.

---

The repositories I maintain are worked on by AI agents as much as by me, which multiplies the places a rule can live. Prose-or-CI stretches into a five-rung ladder, codified in the standards library of kanon, the system that runs the forge, the lint engine, and the audit machinery for my repositories. The placement document is named TEKHNE.md, after tekhne, the Greek word for craft: the knowledge of how a thing is well made. Its spine is one table.

| Rung | Home | Precondition | Test |
|---|---|---|---|
| 5 | hook / gate | mechanical invariant, enumerable failures, catastrophic when wrong | a known-bad fixture is blocked |
| 4 | tool | repeatable multi-step procedure, stable input→output contract | call counts and error rates |
| 3 | durable context | judgment or doctrine that resists deterministic encoding | a fresh reader reconstructs the same judgments |
| 2 | thin config | ephemeral values for one task: which issues, which crate, which lanes | a golden render |
| 1 | one-off prompt | truly one-off, never recurs | none — the last resort |

The placement rule is a single sentence: every behavior settles at the hardest rung whose precondition it meets. The preconditions do the work. A rule earns the gate rung only when it is mechanical and its failure modes can be enumerated. Doctrine that resists deterministic encoding stops at the context rung no matter how much anyone cares about it.

The test column is the ladder's check on itself: every rung above the bottom carries a way to catch its own failure. The bottom rung has no test. That is the reason a one-off prompt is the last resort, not a gap in the table.

---

The first law governs behaviors sitting too soft. A behavior on a softer rung that meets a harder rung's precondition is a defect - the demotion law says move it to the harder rung. Once it lands there, the prose that used to state it is dead weight, and the law says to delete it, because a hook-enforced rule restated in a document is a second copy of a fact that now has a canonical home, and second copies drift. The consequence runs against instinct - the documentation shrinks as the system hardens.

Most rules split instead of moving whole. One writing standard in my fleet flags hedge-word clusters: two or more hedge words within ten words of each other. The enumerable half of that rule, the word list itself, meets a harder rung's precondition, so the list compiled into a lint rule, and the linter now names the words and the line. What stayed behind in the standards document is the residue no regex can hold: whether a sentence hedges structurally, parking uncertainty beside a claim without using any listed word.

---

The second law is the stop. A behavior a gate can only check a proxy for must not be pushed onto a hook, because the proxy misfires on exactly the edge cases that matter: whether a change's stated scope matches its blast radius has cheap proxies, and every one is wrong precisely where the question gets hard. Forcing the judgment down builds a gate that certifies the proxy while claiming to certify the property, which is worse than no gate. No gate leaves the question visibly open. The proxy gate closes it falsely.

My own system supplied the cautionary instance. An assessment of kanon's quality machinery found a cluster of writing rules - about forty word-bans plus filler and minimizer checks - attacking vocabulary as a stand-in for the quality property itself, with the teeth misplaced around them: about four rules blocked merges while more than a hundred warned into logs nobody read. ADR-011 names the correction, but at `d5eab9fac35c` it remains roadmap work: classify each rule as substance or proxy, allow only substance rules to block a merge, and add an Advisory tier for checks that cannot be made substance-faithful. The landed severity enum still has only Error, Warning, and Info. Naming a proxy as a proxy is the intended honest placement, not a completed enforcement mechanism.

The two laws describe one defect seen from opposite directions, and both substitute a proxy for the property they claim. The placement that avoids both is the discipline's whole content: the hardest rung at which the behavior stays both enforced and true.

---

Placement needs an admission test, and the one kanon's decision records use is reflexive: no lint rule and no design document is admitted unless passing it means the property is present, not a proxy satisfied. The record that established the bar applied it to its own text and struck an unfalsifiable superlative about itself from an earlier draft. The decisive question at admission never changes: does the thing exhibit the property it claims, or assert it? A vault that stores plaintext asserts. The question sounds philosophical until it catches something running.

It caught the judge. kanon includes a judge contract for semantic findings. The landed source is narrower than the redesign: `elenchos` defines typed candidates and verdicts, requires a verified citation before a strong-tier semantic judge runs, and provides a generic labeled holdout type of ten to twenty mixed confirm/reject cases with deterministic scoring. Those types and tests are real. They establish a contract shape and a reusable holdout subset, but they do not yet establish a fully grounded, per-kind calibrated judgment system.

The remaining redesign is the ladder applied to that boundary. Evidence-byte tokens and token-echo rejection, automatic widening when evidence is insufficient, committed calibration registries per claim kind, inverted-claim controls, deterministic replay as a gate, and the named `WORKFLOW/judge-uncalibrated` rule remain sequenced work. Until those mechanisms land together, the generic holdout must not be described as if it binds every verdict to evidence and calibration.

The intended gate leg is deterministic: fail on a flipped known case, never on a live model call. The verdict itself, the genuinely non-mechanical step, remains a judgment. The ladder can harden everything around it without pretending the target is already present.

---

One class of behavior overrides both laws. "Is this operation safe to run right now" is a judgment call, and the second law would place judgment in context. For irreversible operations - a firmware write, a force-push, a release merge, a mutation of branch protection - the ladder refuses its own logic, and the limits sit at the gate rung permanently, as hard policy, even though the gates holding them are blunt and over-block. Everywhere else, placement follows checkability, but here it follows what a single wrong pass costs. A discipline built on demotion keeps exactly one class it refuses to reason about, because a system clever enough to argue its way past its own safety floor eventually will.

---

The ladder's least obvious consequence is about tone. Durable context is written calm and explicit, with the motivation stated, not in imperative capitals. A context document that shouts (`CRITICAL`, `MUST`, `NEVER`) degrades the agent reading it: the model reads volume as stakes and escalates, asking for confirmation it does not need, fanning out subagents where one would do. That is observation from operating these systems daily, not received prompt-engineering wisdom.

The shouting is also a diagnostic. An invariant that seems to deserve capital letters is one somebody believes must never fail, and that belief is the gate rung's precondition knocking. A gate does not read tone. Once the invariant is mechanical the register question dissolves, and what remains in prose can afford to explain itself quietly, because nothing rides on whether prose is obeyed, and everything that could ride on obedience has been moved somewhere obedience is not optional. The loudest register on the softest rung, the shouted one-off prompt, is the worst case the ladder names: soft and mistuned at once. Calming the register and hardening the rung are the same move.
