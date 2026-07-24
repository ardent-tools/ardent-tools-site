+++
title = "The budget that had to be measured"
description = "A concurrency gate for worker-agent builds, four production melts, one repeated measurement - a full-workspace build costs about twice its declared parallelism."
date = 2026-07-24

[extra]
components = "How a build-concurrency gate learned its own real cost, one production failure at a time."
tier = "notes"
words = "~1050 words"
+++

Two full-workspace builds running at once on a shared build box are enough to push the load average to 184. Add a third and it reaches 223, and for several minutes the box stops answering ssh at all - nothing to kill, nothing to inspect, just a wait for one of the builds to finish on its own. I run a queue of worker agents against that box, and every finished task ends the same expensive way - a full build-and-test pass before anything merges. Nothing stops two of those passes landing in the same minute except a script that has to decide, for each finished task, whether the box has room for one more.

The rule that mattered here also lives in a runbook, one line among many - don't run two full-workspace builds at once. That's the kind of rule that belongs at [the hardest rung its own precondition allows](/writing/hardest-honest-rung/) - mechanical, its failure modes enumerable, catastrophic when it's wrong. A sentence in a document nobody re-reads under deadline pressure is not that rung. The gate is the version that actually holds - admission control runs on every build whether or not anyone remembers the sentence.

---

The first version of the gate checked the box's load average once, then admitted a build if the number came back low enough. Nothing separated the check from the admission. Two agents finishing work in the same few seconds could read the same low number and both get waved through - the gap between looking and acting, with nothing closing it. It also counted admitted slots, not the cores those slots would use - a one-file build and a full-workspace build occupied the same single slot on the same counter, as if they cost the same thing.

The fix I wrote next replaced the load check with an actual budget. Sum the cost of every build currently running, admit a new one only if the running total plus its own cost stays under a fixed share of the box's cores, and check all of it under a lock so two admissions can't race into the same window again. Cost, at first, was set to whatever parallelism a build declared for itself - a full-workspace build declaring twelve threads counted as twelve. Two of those, admitted together under a budget sized to roughly eighty percent of the box's cores, looked safe on paper and still drove the load average to 48.

A full-workspace build doesn't stop at the parallelism it declares. Its own compile runs alongside a format check, a lint pass, and a test runner that spawns its own processes, and all of it stacks threads past whatever number got set. I measured the actual peak against the same box - close to twice the declared figure, about 24 cores for a build that declared 12. That number, not the declared one, is what the budget needed to charge. The number that mattered here has a different pedigree than [a count triangulated three ways elsewhere](/writing/three-ways-to-count/) - one method, the same load-average reading, run again each time the previous figure turned out to be an assumption instead of a fact.

---

The fix generalizes instead of hardcoding a workaround for one box. A full-workspace build's cost is set to twice its declared parallelism, and admission becomes a straight division - how many builds of that cost fit under the budget, rounded down.

```bash
# a full-workspace build's real core footprint runs about 2x its declared
# parallelism (measured: two full builds at parallelism=12 drove load to
# 48, roughly 24 cores each)
if is_full_workspace; then
  cost=$(( declared_parallelism * 2 ))
else
  cost=$declared_parallelism
fi

# admission auto-scales to the box - no hardcoded per-box ceiling
concurrent_full_builds=$(( budget / cost ))   # floor division
```

A 32-core box works out to a budget around 25 and a full-build cost around 24 - one concurrent full build, the same number the earlier fix reserved the whole budget to guarantee. A box with 180 cores works out a budget of 144 and a full-build cost of 48, and the same division admits about three full builds running side by side. Nobody wrote a branch in the admission math for the bigger box. The formula already had room for it, and only the cost, measured once per box, changes.

---

The fix that stopped the melt created a slower failure. The safest reading of "one full build at a time" reserved the entire budget the moment a full build started, so nothing else could run beside it - correct under load, and also the reason a full build arriving into a box already busy with a continuous stream of small scoped builds could wait indefinitely. Small builds kept finishing and starting faster than the full build's own check ever caught a gap wide enough to admit it. Nothing was blocking it on purpose. The box just never reached zero, and a box that never reaches zero on its own is starving something while everything else looks busy and healthy.

The fix gives a waiting full build a way to announce itself before it's admitted. It drops a marker file the moment it starts waiting, and every small build's own admission check looks for that marker first. A small build that sees one waiting yields, even with budget technically free for it, so the running total drains toward zero instead of refilling behind it. Full builds never yield this way to each other, only small builds yield to a waiting full build - and once it holds the budget it needs, it runs.

---

All of this state is files in one directory, not a service, because a directory of files is the concurrency primitive a shell script actually has - and it has one specific way to leak. A build gets killed mid-run, and whatever file it dropped to reserve its share of the budget, or to mark itself as a waiting full build, doesn't get cleaned up by anything, because the process that would have cleaned it up is the one that's gone. Every admission check reads those files back off disk and tests, for each one, whether the process that wrote it is still alive. A file whose process is dead gets deleted on the spot, by whichever check happens to read it next - not a separate cleanup job, which would be one more thing that could itself die mid-run. A killed build's reservation and its waiting marker both disappear the next time anything asks whether they're still real.

---

The complete fix history is four rows, one melt each.

| # | What broke | What fixed it |
|---|---|---|
| 1 | A load average checked once, then a slot admitted on it - two builds could read the same low number in the same window | A shared core budget, checked and reserved under a lock |
| 2 | Two full builds costed at their declared parallelism still doubled the load past what the budget assumed | Cost set to twice the declared parallelism, admission by budget divided by cost, rounded down |
| 3 | A full build waiting behind a continuous stream of small builds, the budget never draining to zero | A waiting-marker file - small builds yield to it, a full build yields to nothing |
| 4 | A killed build's reserved budget and waiting marker outliving the process that wrote them | Every admission check tests the owning process and reaps the file if it's dead |
