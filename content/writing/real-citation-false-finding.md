+++
title = "The citation was real - the finding wasn't"
description = "Citation-verification confirms a quoted line exists at the place a finding names, and says nothing about whether the conclusion built on that line is true."
date = 2026-07-24

[extra]
components = "A citation can check out at the substring level while the conclusion built on it stays false."
tier = "research"
words = "~1150 words"
+++

Citation-verification checks one fact. The string quoted in a finding is really there, at the file and line named. It does not check whether the story built on that string is true. I built the tool that runs this check inside kanon's audit pipeline, and the distinction turned load-bearing the day a run I trusted put 31 findings through it, watched all 31 pass, then refuted 28 of them on a second, harder pass.

---

The check lives in one function, `judge_one`, in `crates/angelos/src/tools/audit/judge.rs`. It reads a `file_lines` citation such as `src/lib.rs:2`, opens the file, and asks whether the claimed substring appears there. If it does, `claim_present` comes back true. That is the whole contract - not "is this a real defect," just "does this quote match this line." The module's own comment says as much - the tool reads the cited location plus surrounding context "so an orchestrator agent can adversarially assess whether a finding's conclusion is true (not just that the citation is present)." A citation can be exact and the conclusion can still be wrong. The code was written already knowing that.

The check also refuses to pass what it cannot check. A `file_lines` value with no line number - a bare path, a directory - sets a `vague_location` flag and a `VAGUE_LOCATION` guard on the returned context, and nothing downstream may auto-file a finding carrying it. The refusal is mechanical and total. It is also narrow. It catches a finding that names no location. It does nothing for a finding that names a real, precise, correct location and draws the wrong conclusion from what sits there - the common failure, not the rare one.

---

A run against kanon on 2026-06-22 produced 31 candidates that had already cleared citation-verification - 31 quotes, all real, all sitting exactly where each finding said they sat. Those 31 went on to a second pass - a strong model reading each cited location in context, told to assume every finding false until the surrounding code proved otherwise. 28 came back refuted. Three more were real but rated too high, and were corrected down. None of the 31 survived the second pass at its original rating.

| Outcome | Count |
|---|---|
| Citation-verified candidates | 31 |
| Refuted by the adversarial judge | 28 |
| Real, severity corrected down | 3 |
| Real, upheld as originally rated | 0 |

Crypto and kernel-adjacent code produced the worst of it, the surface where a plausible-sounding defect and a real one read almost identically to a model pattern-matching on shape instead of tracing control flow. Nothing in the run was a bad citation or a formatting slip. Every one of the 28 refuted findings had already passed the check that confirms its quote is real.

---

The judge names its own refutations, and the three most common line up with three ways a citation stays honest while the conclusion built on it goes false. An inverted_claim cites a real guard clause and reads it backward - the finding calls a validated path unvalidated, and the cited line is the validation. A hallucinated_location cites a real line whose text happens to match the finding's wording without being the line the finding is actually about, so the defect described, if it exists at all, lives somewhere the citation never points to. An over_rated finding gets the defect right and the blast radius wrong - a real gap gated by a caller three functions up, filed as though nothing stood between it and production. All three pass citation-verification identically. Matching a substring says nothing about whether a reading runs backward, whether a citation lands in the right neighborhood, or whether a gap is actually reachable.

---

The second pass had its own failure mode, and finding it took a further run. The judge reads thirty lines around a citation as a head start, cheap enough to run at scale - but a claim like "never validates" or "leaks on every error path" describes a whole function, and thirty lines on either side of one cited line does not always cover one. A batched version, run against kanon on 2026-06-24 and reading only that fixed window, wrongly refuted real findings as inverted or unverifiable, including a high-severity finding on an auth gate. The window that made the judge cheap was also cutting it off from the evidence it needed.

The fix widens the window on demand - when a claim reads as whole-function in scope, the judge reads the full function and its call sites instead of stopping at thirty lines. Checking that change needed a control the first run never had - five inverted claims, built to fail, where the correct verdict was refute and nothing else. The read-when-narrow judge refuted all five. Run against the same batch the window-only version had wrongly cleared, it restored ten findings out of ten, including the auth-gate finding, at four to five times fewer agents than judging one candidate per agent.

---

`audit_judge` and `audit_batch_judge` are both live, registered in angelos's tool router, callable today, doing exactly the context-assembly work described here. What they do not do is decide anything. The verdict - refute, uphold, correct the severity - stays an orchestrating model's judgment call, not a mechanical gate a bad answer cannot pass. A calibrated version, bound to per-claim evidence and checked by deterministic replay against a committed set of known-good and known-bad cases, is designed - the shape is written down - and not yet built. The severity a verdict carries has three values today - error, warning, info - and none of them means judged-and-calibrated. That gap is not an oversight. Forcing an uncalibrated judgment down into a hard gate would trade a visibly open question for one a green checkmark quietly answers wrong, the same trade the ladder in [The hardest honest rung](/writing/hardest-honest-rung/) refuses on principle.

---

Every stage here - finder, citation check, judge, the further run that caught the judge's own blind spot - produces a self-report, and every one of those self-reports was checked against something outside itself before it got believed - the citation against the file, the verdict against a control set built to fail, the fix against the exact findings the earlier version got wrong. That is the same shape [Three ways to count the same thing](/writing/three-ways-to-count/) found in an unrelated question about counting tools on a running server - a self-report is not evidence about itself, no matter how confidently it cites its own sources. A pipeline that points a model at a codebase and asks it to file what it finds is making a bet citation-verification alone cannot cover - that a model able to quote a line correctly has also reasoned about that line correctly. Citation-verification was built to answer the first of those two questions. Nothing in the pipeline gets to skip the second one because the first one passed.
