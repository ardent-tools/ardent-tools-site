+++
title = "Coordination that isn't voting"
description = "Voting and hub-orchestration are the two default shapes of multi-agent coordination, and the arithmetic that breaks voting on hard tasks is why a third shape needs its own emergence conditions."
date = 2026-07-20

[extra]
tier = "research"
components = "Why voting and hub-orchestration both fail on hard tasks, and a third coordination shape that isn't a blend of them."
figure = "/img/coordination-shapes.svg"
figure_alt = "Three coordination shapes side by side: vote, where isolated agents fan in to an aggregator with no connections between them; hub, where a hub farms pieces out to workers and assembles them back with no lateral edges; and lateral, where agents influence each other during solve before an integrator composes."
words = "~1470 words"
+++

Nearly every multi-agent system ships in one of two shapes. In the first, the same problem goes to every agent, each works alone, and an aggregation step combines the finished outputs: majority vote, best-of-n selection, a judge ranking candidates. In the second, a hub decomposes the problem, farms the pieces to workers, and assembles what comes back. Ensembles and model juries are the first shape. Nearly every orchestration framework is the second.

Each shape hides its load-bearing assumption in the step nobody diagrams. Independent-then-aggregate assumes the agents' errors are independent - that where one goes wrong, the others don't go wrong the same way, so errors cancel and signal accumulates. Hub orchestration assumes the decomposition is right - that the hub saw everything that mattered before it split the work, and that no piece changes the meaning of another piece mid-solve. Both assumptions fail on the hard end of the task distribution, and the first fails by arithmetic.

---

The Condorcet jury theorem is usually quoted in its flattering direction - when each voter independently exceeds one-half accuracy on a binary question, majority accuracy climbs toward certainty as voters are added. Below one-half the same algebra runs backward, where the majority is worse than any single voter, and adding voters drives it toward certain error at the rate it once climbed toward certain truth. That threshold is not a technicality. The small models that make thousand-agent parallelism affordable sit below one-half accuracy on hard tasks, in the inverted regime, so on exactly the problems a large ensemble was supposed to help with, every agent added makes the answer worse.

Voting carries a second limit that no accuracy fixes. A vote selects among answers already produced, and no voting scheme can return an answer nobody voted for. Whatever the aggregate outputs was already sitting in some agent's output. Emergence under voting, an answer beyond every individual, is zero by construction.

---

The independence assumption fails from the other end too. Sampling temperature is the cheapest diversity - one model drawn from many times, one function by definition, whatever the variance in its outputs. The next-cheapest got measured in January 2026. BatchEnsemble gives each ensemble member a small learned perturbation of one shared weight set, and Zamyatin et al., asking *Is BatchEnsemble a Single Model?*, found the members "near-identical in function and parameter space, indicating limited capacity to realize distinct predictive modes." Members that share weights share failure modes. Short of structural diversity, different computations, not one computation sampled differently, the jury theorem's independence premise is never met, and its flattering direction never applies.

---

A third shape exists, and it is not a blend of the first two. In the first shape, agent A finishes its piece, agent B finishes its piece, and mutual influence begins after both are done, which is to say never, since the aggregator sees finished outputs, not searches. In the third, A's partial state constrains B's search space while B is still searching, and B's constrains A's. The candidate solutions co-evolve under each other's constraints and arrive jointly shaped. The result is one answer that two searches produced under mutual pressure, not two separate answers merged after the fact.

Binocular depth perception is the working model. The visual system does not render one finished image per eye and average the two into a third image. It computes depth from binocular disparity, the small geometric disagreement between the two views, while the views are being processed. Neither eye's image contains depth. The depth is in the difference between the streams, and it is extracted during processing, laterally, not from the finished pictures. Average the finished pictures instead and the result is a double-exposed photograph, and the disparity that carried the information is exactly what averaging destroys.

Coupled solvers create a joint constraint space that is a different object from the union of their separate constraint spaces. A design that reads clean and carries its load, while still being cheap to machine, is rarely found by solving form and statics separately from what manufacturing can actually cut - the intersection is usually empty, and when it isn't, it is a compromise none of the three searches would have generated on its own. Coupled solving reaches points the separate searches never propose, because each domain's constraints steer the others' searches toward the mutually feasible region from the first step.

---

Lateral influence during solve gets claimed more often than it gets built - an architecture can carry "agent communication" that is voting with extra round trips. While specifying a system of my own, I wrote down three conditions that separate the third shape from decorated versions of the first two. They are phrased for that system's aggregation layer, and nothing in them is specific to it.

| # | Condition | What it excludes |
|---|-----------|------------------|
| 1 | Lateral connections exist: units influence each other during solve, not only through a parent | Pure hierarchy. Hub-and-spoke has no lateral edges, whatever the diagram shows |
| 2 | Aggregation is nonlinear | Averaging. A weighted average of unit outputs stays inside the convex hull of those outputs; the combined answer cannot leave the region the individual answers span |
| 3 | Aggregation follows the connection structure | Combining along edges that don't exist. If which-unit-constrains-which carries information, aggregation that ignores the wiring destroys exactly that information |

The second condition carries a constructive proof. Three agents emit two-dimensional outputs, call the axes confidence and novelty, and working independently, none exceeds 0.8 novelty. Let one agent condition its output on the disagreement signal between the other two, and its novelty reaches 1.04, outside every weighted average of the independent outputs. This is an existence proof, not a performance claim - it shows the hull can be escaped, not that a given system escapes it. Pure averaging provably stays inside, and so do contractive update rules, where iterated communication that pulls outputs toward each other lands on a fixed point the hull already contained.

The same condition audits a shipped system in one step. Find the aggregation step. If it is a weighted average, the combined answer sits inside the region the agents' final answers span - whatever happened during the conversation, the output cannot be beyond every agent's own.

---

The defensible middle ground is orchestrated search, the hub shape run honestly. Monte Carlo tree search runs thousands of rollouts, each steered by what earlier rollouts learned - sequential constraint, not independent ballots. AlphaGo makes the tradeoff concrete. Its rollout policy predicted expert moves at 24.2 percent accuracy, well under the 57.0 percent of the slower policy network it could have used, and the cruder one was the right call - at two microseconds per move against three milliseconds, the search fits enough more rollouts under a fixed budget that the faster evaluator wins (Silver et al., Nature 2016). The quantity worth maximizing was rollouts per second, not accuracy per rollout.

An ant colony's foragers deposit constraint on each other's searches as they go. A jury, valued correctly, is the same pattern, and the point of twelve jurors is spread of perspective under one shared body of evidence, not the hope that juror nine is brilliant. In each case the units are supposed to differ, so no independence assumption is being violated off-stage, and an integrator composes rather than selects, so the ceiling is not the best individual ballot. Shipped systems stop here for a budget reason, not a conceptual one - lateral edges are communication during solve, and a full mesh of them grows quadratically with unit count.

A private architecture project of mine, Gnomon, named for the part of a sundial that casts the shadow, sits in that middle mode after trying to sit further out. Its coordination design aimed at the third shape, thousands of small worker units sharing partial state during solve. The cheapest substrate bet, that the routing structure of a large teacher model could be extracted and used to specialize the workers, died under two pre-registered spectral tests, and [that result has its own essay](/writing/gnomon-falsification-tests/). Orchestrated search survived - one integrator evaluating structurally diverse exploration trajectories. The third shape stays in the specification as a design condition, not a result, and its falsifier is written before any of the reframed architecture exists - structural specialization has to produce measurably lower correlation between workers than standard fine-tuning at matched output quality, or the decomposition loses its engineering justification a second time.

Condition one has already bitten there once. An early engineering pass on the lateral mechanism quietly centralized it - collect-then-aggregate wearing the name "shared awareness" - and the design review's diagnosis fits in one line, the pass solved the bandwidth problem by deleting the mechanism it was meant to carry.
