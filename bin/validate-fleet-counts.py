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
    """Ground truth, from the derived catalog.

    The catalog is the authority for all three numbers: it carries a `group` per
    entry and a `private` flag, which is exactly the shape the claims describe.
    The meta-repos never enter it, so no exclusion list is needed here.
    """
    systems = json.loads(CATALOG.read_text())["systems"]

    featured = [s for s in systems if s.get("group") == "systems"]
    public = [s for s in systems if not s.get("private")]
    featured_public = [s for s in featured if not s.get("private")]

    # The control-plane config is a fact about the repository, not the catalog,
    # so it is read from the working tree when present. Absent a clone, the
    # claim cannot be checked and saying so is the honest result.
    with_config = 0
    unreadable = 0
    for s in featured_public:
        repo = ROOT.parent / s["name"]
        if not repo.is_dir():
            unreadable += 1
            continue
        if (repo / CONTROL_PLANE_CONFIG).is_file():
            with_config += 1

    return {
        "featured_systems": len(featured),
        "public_repos": len(public),
        "featured_public_with_control_plane": with_config,
        "_unreadable_repos": unreadable,
    }


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
    unreadable = truth.pop("_unreadable_repos", 0)
    problems: list[str] = []
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
    if unreadable:
        print(f"  note: {unreadable} featured repo(s) not present locally, so their "
              f"control-plane config could not be read; the count above is a floor")

    if problems:
        print(f"\nFAIL: {len(problems)} fleet-count problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print("PASS: fleet counts in copy agree with the derived catalog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
