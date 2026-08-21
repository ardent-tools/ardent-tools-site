#!/usr/bin/env python3
"""Validate factual invariants in text extracted from the tracked résumé PDF."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from career_claim_contract import QUANTITY_TOKEN  # noqa: E402


def normalized(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(errors="replace")).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", type=Path, help="pdftotext output")
    args = parser.parse_args()
    text = normalized(args.text)
    folded = text.casefold()
    errors: list[str] = []

    required = (
        "private case study",
        "public receipt",
        "clean-room rust implementation",
        "configured llm provider",
        "301,000 icd-10, cpt, hcpcs, and snomed codes",
    )
    # Literal phrases: these ARE the claim. There is no other way to write
    # "built directly from the go source" that means the same thing, so a
    # substring is the right instrument.
    forbidden = (
        "open source",
        "no external services",
        "built directly from the go source",
        "60,000+ service members",
    )
    # Claim-bound patterns: these are FACTS with many renderings, and a
    # substring guards a spelling rather than the fact (forkwright#168). The
    # withdrawn training-pair count was recorded here as "1.35 million", which
    # a rewrite to "1.35M", "1,350,000" or "$1.35M" walks straight past while
    # the check still reports green. Each pattern pairs a quantity with the
    # thing it quantifies, using the same QUANTITY_TOKEN the career-claim
    # validator uses, so the two cannot disagree about what a number looks like.
    forbidden_claims = (
        (
            "training-pair count",
            re.compile(
                rf"(?:\b{QUANTITY_TOKEN}\b[^.\n]{{0,60}}\btraining[ -]pairs?\b|"
                rf"\btraining[ -]pairs?\b[^.\n]{{0,60}}\b{QUANTITY_TOKEN}\b)",
                re.IGNORECASE,
            ),
        ),
        (
            "cluster-purity figure",
            re.compile(
                rf"(?:\b{QUANTITY_TOKEN}\s*%[^.\n]{{0,60}}\bcluster purity\b|"
                rf"\bcluster purity\b[^.\n]{{0,60}}\b{QUANTITY_TOKEN}\s*%)",
                re.IGNORECASE,
            ),
        ),
    )
    for phrase in required:
        if phrase not in folded:
            errors.append(f"resume text lacks required factual phrase: {phrase!r}")
    for phrase in forbidden:
        if phrase in folded:
            errors.append(f"resume text retains disputed or false phrase: {phrase!r}")
    for topic, pattern in forbidden_claims:
        match = pattern.search(text)
        if match is not None:
            errors.append(
                f"resume text retains withdrawn {topic}: {match.group(0)!r}"
            )

    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    sys.stdout.write("PASS: resume PDF non-career factual guard\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
