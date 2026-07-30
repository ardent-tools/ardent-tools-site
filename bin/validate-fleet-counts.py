#!/usr/bin/env python3
"""Prove the fleet counts stated in prose against the catalog they describe.

Usage: python3 bin/validate-fleet-counts.py

Three numbers appear in site copy - how many systems are featured, how many
public repositories the fleet holds, how many of the featured systems carry the
control-plane config. Each was hand-typed in more than one page, and a single
repository flipping visibility falsifies all three at once with nothing to catch
it.

The numbers stay in prose because a reader should meet them mid-sentence, not
follow a link. This proves them instead of deriving them into a template: the
copy is the surface, the catalog is the authority, and a disagreement fails the
gate.

A site whose subject is verification cannot carry an unverified count. That is
the specific self-refutation its own voice contract names.

Two legs, because the portable one is weaker than the true one. The counts are
derived from the catalog, which every checkout has, so the copy is checked
everywhere including CI. Where a sibling clone happens to be reachable, the
catalog's own `kanon_ci` declaration is additionally checked against a real
`.kanon-ci.toml`, because a declaration agreeing with a declaration proves
nothing about the repository. The second leg is skipped when no clone is
present, and its absence is reported rather than passed over.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "static/systems.json"
SYSTEMS_DIR = ROOT / "content/systems"
CONTROL_PLANE_CONFIG = ".kanon-ci.toml"

# Repositories that exist to hold org furniture rather than a system: the org
# profile and the shared-workflow repo. A count of "the fleet" that includes
# them is counting the filing cabinet.
META_REPOS = {".github", "forkwright"}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20,
}
WORD_ALT = "|".join(NUMBER_WORDS)

# Each claim: a regex over site copy with one capture group holding the number,
# and the name of the derived value it must equal. The regex is deliberately
# tight - a loose pattern that stops matching after a rewrite reports success
# for a claim it is no longer reading.
CLAIMS = (
    # Tight on purpose. "Two systems are the exception - they belong to my prior
    # employer" is a different claim about ownership, and a pattern loose enough
    # to catch the fleet count catches that too. Rewording the real sentence
    # makes this stop matching, which the zero-match guard below turns into a
    # failure rather than a silent pass.
    ("featured_systems",
     re.compile(rf"\b({WORD_ALT})\s+systems,\s+the\s+libraries", re.I)),
    ("public_repos", re.compile(rf"\b({WORD_ALT})\s+public\s+repositor", re.I)),
    ("featured_public_with_control_plane",
     re.compile(rf"\b({WORD_ALT})\s+featured\s+public\s+system\s+repositor", re.I)),
)


def derive() -> dict[str, int]:
    """Ground truth for the stated counts, from the derived catalog.

    Every checkout has the catalog, so all three counts resolve in CI. The
    control-plane count reads the `kanon_ci` field the catalog carries per
    entry; `audit_declarations` is what tests that field against reality.
    """
    systems = json.loads(CATALOG.read_text())["systems"]

    featured = [s for s in systems if s.get("group") == "systems"]
    public = [s for s in systems if not s.get("private")]
    featured_public = [s for s in featured if not s.get("private")]

    return {
        "featured_systems": len(featured),
        "public_repos": len(public),
        "featured_public_with_control_plane":
            sum(1 for s in featured_public if s.get("kanon_ci")),
    }


def audit_declarations() -> tuple[list[str], int]:
    """Test the catalog's control-plane declaration against the repositories.

    A count derived from a field the same author typed is a consistency check,
    not a verification. This is the leg that makes it one, and it can only run
    where the repository is on disk.
    """
    systems = json.loads(CATALOG.read_text())["systems"]
    problems: list[str] = []
    checked = 0

    for s in systems:
        if s.get("group") != "systems" or s.get("private"):
            continue
        repo = ROOT.parent / s["name"]
        if not repo.is_dir():
            continue
        checked += 1
        actual = (repo / CONTROL_PLANE_CONFIG).is_file()
        declared = bool(s.get("kanon_ci"))
        if actual != declared:
            problems.append(
                f"{s['name']}: catalog declares kanon_ci={declared} but "
                f"{CONTROL_PLANE_CONFIG} is "
                f"{'present' if actual else 'absent'} in {repo}")

    return problems, checked


def surfaces() -> list[Path]:
    out = []
    for pattern in ("content/**/*.md", "static/llms.txt"):
        out.extend(p for p in ROOT.glob(pattern) if p.is_file())
    return sorted(out)


def main() -> int:
    if not CATALOG.is_file():
        print(f"FAIL: {CATALOG.relative_to(ROOT)} missing; run "
              "`python3 bin/site.py sync` first", file=sys.stderr)
        return 1

    truth = derive()
    problems, ground_truthed = audit_declarations()
    seen: dict[str, int] = {name: 0 for name, _ in CLAIMS}

    for path in surfaces():
        text = path.read_text(errors="replace")
        rel = path.relative_to(ROOT)
        for name, rx in CLAIMS:
            for m in rx.finditer(text):
                seen[name] += 1
                stated = NUMBER_WORDS[m.group(1).lower()]
                if stated != truth[name]:
                    line = text[: m.start()].count("\n") + 1
                    problems.append(
                        f"{rel}:{line} states {m.group(1)} for {name}; "
                        f"derived value is {truth[name]}")

    # A claim nobody states is not proof of health - it means the regex has
    # stopped reading the copy, which is the failure this check exists to avoid.
    for name, count in seen.items():
        if count == 0:
            problems.append(
                f"no surface states `{name}` - either the copy was rewritten and "
                f"this validator no longer reads it, or the claim was dropped. "
                f"Derived value is {truth[name]}.")

    for name, value in truth.items():
        print(f"  {name} = {value} ({seen[name]} statement(s) in copy)")
    if ground_truthed:
        print(f"  {ground_truthed} control-plane declaration(s) checked against a "
              f"real {CONTROL_PLANE_CONFIG}")
    else:
        print(f"  note: no sibling clone reachable, so no control-plane declaration "
              f"was checked against a real {CONTROL_PLANE_CONFIG}; the count above "
              f"rests on the catalog's own field")

    if problems:
        print(f"\nFAIL: {len(problems)} fleet-count problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print("PASS: fleet counts in copy agree with the derived catalog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
