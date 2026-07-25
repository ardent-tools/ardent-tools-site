+++
title = "The checkpoint that hashed correctly and still lost a file"
description = "A compaction step in this site's own release ledger could carry a correct digest and still drop a retained asset - the fix needed a second, independent check the first one never asked."
date = 2026-07-24

[extra]
components = "A root-digest check bound a checkpoint to its prior ledger - it never checked what the checkpoint kept."
tier = "research"
words = "~1200 words"
+++

A hash check can be logically necessary for an integrity property and still not establish it. The distinction sounds like a whiteboard argument until a compaction step in this site's own release ledger built the failure mode for real - a checkpoint entry that hashed to exactly the right value while it had already dropped a file it was supposed to keep. The fix landed in commit a2f9dce.

---

This site addresses every static asset - css, fonts, the vendored player - by the content itself. A file's public URL is `/a/<its own sha256>.<extension>`, so editing one byte of a stylesheet gives it a new address, and the old one stops being anything the current build serves. That covers the current page, which always links to the current address. An RSS entry published months ago, an external bookmark, a cached copy on someone else's server - none of those update when the build does, and content-addressed publishing has no native memory of what it used to serve. Something has to keep the old bytes around and prove it, or those links stop resolving without warning.

`asset-retention.json` is the ledger that keeps that promise, and `retained-assets/` is where the old bytes actually live. CI's retention-authority step runs `bin/asset_retention.py verify` on every push and pull request, checking the checked-in ledger against a trusted prior version read from an independently selected earlier revision - ordinarily the previous commit, `HEAD^` when a recovery dispatch is what's running the check. The rule is append-only. Every entry the prior ledger held, the current one must still hold, byte-for-byte, in the same order. History under that rule only grows, one entry per commit that touches an asset, so a warning prints at 128 entries and a hard structural ceiling sits at 4096, both there to point at the one sanctioned way out - `compact`, which replaces the whole entry list with a single checkpoint summarizing everything still retained.

---

A checkpoint entry carries two fields that matter here - `resources`, meant to be the union of every physical asset the prior history ever obligated the build to keep, and `checkpoint_root_sha256`, the digest of the last entry in that prior history, the one entry the checkpoint stands in for. Before the fix, `validate_history_prefix()` accepted a checkpoint on one condition. If the checkpoint's `checkpoint_root_sha256` matched the hash of the prior ledger's own last entry, the function returned, and the checkpoint was in.

```python
if (
    prior_entries
    and isinstance(checkpoint, dict)
    and checkpoint.get("kind") == "checkpoint"
    and checkpoint.get("checkpoint_root_sha256") == entry_digest(prior_entries[-1])
):
    return
```

That digest is cheap to check, and it proves something real - it binds the checkpoint to that exact prior state, so a checkpoint minted for a different ledger and replayed here fails immediately. It doesn't touch the checkpoint's own `resources` list at all. Nothing before the fix required that list to contain everything the prior ledger's full history actually held.

---

The gap is buildable, not just arguable. Run `compact` against a genuine two-entry ledger and get back one checkpoint with a correctly computed root digest. Then hand-edit the result - drop one item from `resources`, and delete the matching file under `retained-assets/` so the ledger and the directory still agree with each other. `validate_ledger()` passes this result, because that function only checks that a ledger is internally consistent with what's currently on disk - are the declared files present, do their hashes match what's declared. It has no notion of what an earlier, now-replaced ledger required, so a ledger and a directory that agree with each other but disagree with history read as clean. The root digest is untouched, still equal to the prior ledger's own last entry. The pre-fix `verify` passes too, and the dropped asset is gone.

[The hardest honest rung](/writing/hardest-honest-rung/) argues the general shape in the abstract - a gate that can only check a proxy for the property it claims, built and trusted as if the proxy were the property. This is the literal case. Root-digest matching is a proxy for obligation-preservation, not the property itself, and nothing forced the two apart until a hand-edited ledger turned the gap between them into a failing assertion instead of an argument.

---

The fix adds a second condition, independent of the first. `resource_union()` walks any list of entries and returns the (path, hash) union across all of them - the same computation `record_checkpoint()` already used to build a correct checkpoint's `resources` in the first place, reused here on the verifying side instead of trusted from the checkpoint's author. `validate_history_prefix()` now requires the checkpoint's own resources, taken as a union, to be a superset of `resource_union(prior_entries)` - every obligation the prior ledger's whole history held has to still appear in the checkpoint, unchanged. Superset, not equality - a ledger that already added a new snapshot since the checked-in base was taken, and only compacted afterward, legitimately carries more than the base's union ever named, and that has to keep passing.

| Condition | Checks | Proves alone | Misses alone |
|---|---|---|---|
| Root digest | `checkpoint_root_sha256 == entry_digest(prior_entries[-1])` | this checkpoint claims to summarize exactly this prior history, not another one | whether that summary is complete |
| Superset | checkpoint `resources` ⊇ `resource_union(prior_entries)` | every prior obligation is still named, identically | which prior history the checkpoint is even claiming to summarize |

Each row is necessary. Neither is sufficient by itself. A checkpoint could satisfy the superset row with a large, honest resources list rooted against the wrong ledger entirely - safe, but not verifying the transition CI actually needs proven. A checkpoint could satisfy the root-digest row alone, as the pre-fix code did, and still lose a file.

The shape here isn't the one [three ways to count the same thing](/writing/three-ways-to-count/) used on an unrelated counting problem - three independent methods with no failure mode in common, agreeing, where the agreement itself was the evidence. This pair doesn't agree with itself. The two conditions check different things, neither corroborates the other, and dropping either one reopens exactly the hole it was closing.

---

Run the same hand-edited checkpoint against the fixed code and `verify` fails, naming the exact path it's missing rather than reporting a bare inequality.

```python
missing = sorted(
    output
    for output, digest in prior_obligations.items()
    if checkpoint_obligations.get(output) != digest
)
if missing:
    raise ValueError(
        "asset-retention checkpoint drops retention obligations the "
        f"base ledger held: {sample}"
    )
```

The message caps at five paths with a `(+N more)` suffix beyond that, so a large drop still reads as one line, not a wall of output. The construction that passed before the fix fails now, and the failure names the file.

---

The same commit rewrote the module's own docstring, which had called the root-digest match alone a "cryptographic commitment" strong enough that falsifying it "requires having" the real prior history. That line was true about the digest and false about what the digest was doing the job of. The corrected docstring now states two separate claims where there had been one overclaimed one - the root digest binds the transition, and the superset check is what preserves the obligations.
