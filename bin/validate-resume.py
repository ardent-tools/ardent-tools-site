#!/usr/bin/env python3
"""Validate factual invariants in text extracted from the tracked résumé PDF."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


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
        "157 marines and 12 civilians across seven finance functions",
        "seven-month deployment aboard three naval vessels",
        "3,000-person meu",
        "$350,000 deployed cash budget with zero discrepancies",
        "301,000 icd-10, cpt, hcpcs, and snomed codes",
    )
    forbidden = (
        "open source",
        "no external services",
        "built directly from the go source",
        "1.35 million",
        "97.5%",
        "largest disbursing office",
        "second-largest",
        "ten-nation",
        "15 european and african nations",
    )
    for phrase in required:
        if phrase not in folded:
            errors.append(f"resume text lacks required factual phrase: {phrase!r}")
    for phrase in forbidden:
        if phrase in folded:
            errors.append(f"resume text retains disputed or false phrase: {phrase!r}")

    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    sys.stdout.write("PASS: resume PDF factual manifest\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
