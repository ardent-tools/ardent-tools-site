#!/usr/bin/env python3
"""Validate pinned résumé font inputs and the PDF's embedded font set."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

EXPECTED_FILES = {
    "NimbusSans-Regular.otf": "7c25be4d78155523080ab85b10277150657ff7dabbcad7037bdd536c9b6d0d08",
    "NimbusSans-Bold.otf": "7f33328e6b4d4cd21b45fa625791928c9407dc702db6780e56b09ca9a3ecaa67",
    "LICENSE": "772b1b47eead8722156abaed483154e1dd1137e7035290550cea6444192a2e3f",
    "COPYING": "57c8ff33c9c0cfc3ef00e650a1cc910d7ee479a8bc509f6c9209a7c2a11399d6",
}
EXPECTED_FONTS = {"NimbusSans-Regular-Identity-H", "NimbusSans-Bold-Identity-H"}
PDF_FONT_LINE = re.compile(
    r"^(?P<name>\S+)\s+CID Type 0C\s+Identity-H\s+"
    r"(?P<embedded>yes|no)\s+(?P<subset>yes|no)\s+(?P<unicode>yes|no)\s+"
    r"\d+\s+\d+\s*$"
)
SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")


def expected_manifest() -> str:
    return "".join(f"{digest}  {name}\n" for name, digest in EXPECTED_FILES.items())


def validate_inputs(font_dir: Path) -> list[str]:
    errors: list[str] = []
    manifest = font_dir / "SHA256SUMS"
    if not manifest.is_file() or manifest.read_text() != expected_manifest():
        errors.append("résumé font SHA256SUMS differs from the pinned manifest")
    for name, expected in EXPECTED_FILES.items():
        path = font_dir / name
        if not path.is_file():
            errors.append(f"missing pinned résumé font input: {name}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            errors.append(
                f"résumé font input hash mismatch for {name}: expected {expected}, found {actual}"
            )
    found_fonts = {
        path.name for pattern in ("*.otf", "*.ttf") for path in font_dir.glob(pattern)
    }
    expected_fonts = {
        name for name in EXPECTED_FILES if name.endswith((".otf", ".ttf"))
    }
    if found_fonts != expected_fonts:
        errors.append(
            f"résumé font directory has unexpected font inputs: {sorted(found_fonts ^ expected_fonts)}"
        )
    return errors


def validate_pdffonts(report: str) -> list[str]:
    errors: list[str] = []
    found: set[str] = set()
    for line in report.splitlines()[2:]:
        if not line.strip():
            continue
        match = PDF_FONT_LINE.fullmatch(line)
        if not match:
            errors.append(f"unexpected pdffonts row: {line!r}")
            continue
        name = SUBSET_PREFIX.sub("", match.group("name"))
        found.add(name)
        if any(
            match.group(field) != "yes" for field in ("embedded", "subset", "unicode")
        ):
            errors.append(f"résumé font is not embedded, subsetted, and Unicode-mapped: {name}")
    if found != EXPECTED_FONTS:
        errors.append(f"résumé embedded font set differs: {sorted(found ^ EXPECTED_FONTS)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font-dir", type=Path, default=Path("resume/fonts"))
    parser.add_argument("--pdffonts", type=Path)
    args = parser.parse_args()
    errors = validate_inputs(args.font_dir)
    if args.pdffonts is not None:
        errors.extend(validate_pdffonts(args.pdffonts.read_text()))
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    sys.stdout.write("PASS: pinned résumé font inputs and embedded font set\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
