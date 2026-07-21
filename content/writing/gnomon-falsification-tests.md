+++
title = "The falsification tests that killed Gnomon's central bet"
description = "Two pre-registered kill tests, run before a line of extraction code existed, returned KILL on a private cognitive-architecture project's central bet."
date = 2026-07-20

[extra]
components = "falsifiability · spectral analysis · kill gates"
words = "~1490 words"
+++

A private research project I called Gnomon — after the fixed arm of a sundial, the part that doesn't move and makes the sun's position legible anyway — made one central architectural bet. A large teacher model's routing, the pattern of which internal pathway a given token activates, can be pulled out of its weights, compressed to a few tens of megabytes, and used to specialize thousands of small worker units that all share one frozen backbone. If the bet held, personalizing each unit cost almost nothing beyond that shared backbone.

Every downstream number in the specification, from the memory budget for the routing file to the cost model for the training pipeline, assumed it held. Before I wrote a line of extraction code, I wrote down the number that would kill it.

---

The teacher was Qwen3.5-27B, a dense hybrid model: 48 layers of Gated DeltaNet (a linear-attention-style recurrent design) and 16 layers of ordinary full attention, a 3:1 ratio. There's no mixture-of-experts gate to extract — this model doesn't have one. Routing here meant something narrower and, for the bet, more load-bearing: the query and key projection matrices at every one of the 64 layers, the weights that determine which token attends to which, or in the recurrent layers, what gets written into and read out of the running state. If a teacher's routing carries anything like its trained identity, these are the matrices that would show it.

---

Two tests, both cheap enough to run before any training budget was spent — no GPU, no fine-tune, three of the model's eleven weight-shard files downloaded and parsed on a CPU.

F2 asked whether those projection matrices carry real structure or are statistically indistinguishable from noise of the same shape. For every extracted Q and K matrix I took the full singular value decomposition and computed a normalized effective rank: the squared sum of the singular values over the sum of their squares — a count of how many directions carry real energy — divided by the largest count the matrix's shape allows. The null was random Gaussian matrices of matched shape and initialization variance. The kill line, set before the test ran: a mean normalized rank under 0.3 across all matrices would mean real low-rank structure; over 0.7 would mean the matrices sit close enough to the random baseline that there's nothing extractable there; the range between was ambiguous.

F4 asked a sharper question. If routing captures something specific to a model's trained behavior, two models built on the same architecture but fine-tuned to behave differently should route differently. I ran the same extraction against a second model — a community fine-tune of the same base weights, using a technique called abliteration that suppresses refusal behavior and measurably changes what the model will say — and compared the top singular subspaces of the same Q/K matrices between the two. Kill line: subspace overlap above 0.9 would mean the two models route almost identically despite behaving differently, meaning routing reflects the architecture, not the model trained onto it.

---

Both came back on the kill side of the line I'd drawn.

| Test | Measures | Pre-registered kill line | Result | Verdict |
|---|---|---|---|---|
| F2 — structure | Normalized effective rank of every Q/K matrix vs. a random baseline of matched shape | > 0.7 | 0.7815 mean, against a 0.89–0.95 random baseline for the same shapes | KILL |
| F4 — identity | Top-50 subspace overlap of the same matrices between two fine-tuned variants | > 0.9 | 0.9999999986; mean weight cosine printed 1.00002 | KILL |

F2 is the more ambiguous of the two. The trained matrices were measurably less random than the null — 0.7815 against a baseline of 0.89 to 0.95 for matrices of the same shape, meaning something in training did concentrate the spectrum somewhat. It just didn't concentrate it enough. The bet needed a number under 0.3; what came back sat above the 0.7 line I'd set before running the test, closer to the random end of the scale than the structured end.

F4 left less room for interpretation. Subspace overlap between the base model and the fine-tune came back at 0.9999999986 against a 0.9 kill line — 1.4 parts in a billion short of identical. The mean weight cosine across the same matrices printed at 1.00002, past the mathematical maximum of a cosine, because sixteen of the 128 per-matrix values round above 1.0 in single precision. The difference between the two models' weights is smaller than the rounding error of the arithmetic measuring it.

Two models that behave differently enough that a third party built and published the fine-tune specifically to change that behavior have query and key projections that are numerically indistinguishable at single precision. Whatever abliteration changed, it didn't touch these matrices — or these matrices function as shared scaffolding that this class of fine-tuning doesn't reach either way. Both readings kill the same claim: that routing here captures a model's trained identity rather than its architecture.

---

What the result falsifies is specific: routing separability as a linear-subspace property of the Q/K projections in this teacher, under this operationalization, on these two model variants. It doesn't rule out structure a linear method can't see, and it doesn't answer whether the architecture has any reason left to exist once the mechanism it was built around is gone. That's a separate question, and it got a separate answer.

---

The routing result wasn't the only thing wrong with the original design. A separate line of the same self-review turned up a purely mathematical problem the spectral test hadn't even touched: the architecture's headline mechanism was many small worker units voting, and voting is a bad idea when a single unit's accuracy on a hard task is below chance. Majority vote among agents with per-agent accuracy under 0.5 gets worse, not better, as more agents are added — the Condorcet jury theorem runs backward past that threshold. No amount of extracted routing was going to fix a mechanism that was mathematically dead on arrival before the routing question was even asked.

What survived both kills was a narrower, differently-testable claim: instead of many units voting on the same answer, one integrator evaluates and synthesizes across units that explore differently-scoped regions of a decomposed problem — the pattern behind Monte Carlo tree search, ant-colony methods, and a jury whose value is spread of perspective rather than any one juror's brilliance. That version doesn't need routing to capture a teacher's trained identity.

It does need the worker units to be genuinely different from each other, which is itself a claim someone else had already tested and found wanting for the easy version of diversity: ensemble members that differ only by sampling temperature come back "near-identical in function and parameter space" (Zamyatin and Gartner, testing BatchEnsemble, January 2026) — sampling noise dressed up as diversity. The reframe needs structural difference, not noisier sampling, and it ships with its own kill criterion, written before a line of the reframed architecture exists: if structurally-guided specialization doesn't produce measurably lower correlation between units than standard fine-tuning at matched output quality, the decomposition idea loses its engineering justification a second time.

---

None of this was a one-time audit. The same discipline had already killed a smaller assumption earlier in the same specification: the worker units were sized at 50 million parameters. Guertler and colleagues had already trained a from-scratch 50-million-parameter decoder and published the result in 2024: scores at or below random chance on every standard reasoning benchmark they tried. Literature synthesis put the real viability floor around 125 to 135 million parameters at full precision, and roughly double that again under the 1.58-bit quantization the design wanted, following an empirically observed doubling rule for low-bit quantization relative to full precision. The worker-unit floor rose from 50 million to 270 million parameters, about 54MB per unit, before a single unit had been trained, on the strength of somebody else's published numbers, not a new experiment.

Every load-bearing claim in the specification carries one of three tags: proved from stated assumptions, supported by published results, or conjectural with a falsifier written down at the time the claim was made, not after something went wrong. The current tally, after both kills: thirteen proved, five empirical, eight conjectural. The build plan carries four numbered kill gates — extraction failure, kernel-throughput failure, structural-diversity failure, patch-instability failure — each with its trigger condition decided before the milestone that could hit it, so that when a bad number shows up, there's nothing left to argue about in the room.

---

Gnomon is still in specification. No training run has executed. The reframed thesis has its own gate ahead of it — comparing structurally-guided specialization against a standard fine-tune on inter-unit correlation, at matched quality, before any of the reframed architecture gets built — and that number is already written down too.
