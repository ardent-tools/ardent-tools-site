#!/usr/bin/env python3
"""Derive the public systems catalog from its complete source authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
GENERATOR_VERSION = 1
FRONTMATTER = re.compile(r"^\+\+\+\n(.*?)\n\+\+\+\n", re.DOTALL)


def parse_frontmatter(path: Path, body: bytes) -> dict:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"{path}: frontmatter source is not UTF-8: {exc}") from exc
    match = FRONTMATTER.match(text)
    if not match:
        raise SystemExit(f"{path}: no +++ frontmatter block")
    return tomllib.loads(match.group(1))


def source_paths(root: Path = ROOT) -> list[Path]:
    content = root / "content/systems"
    return sorted(content.glob("*.md")) + [root / "data/exact-system-licenses.json"]


def read_snapshot(root: Path = ROOT) -> dict[Path, bytes]:
    snapshot: dict[Path, bytes] = {}
    for path in source_paths(root):
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"{path}: catalog authority must be one regular file")
        snapshot[path] = path.read_bytes()
    return snapshot


def read_exact_licenses(
    root: Path = ROOT,
    snapshot: dict[Path, bytes] | None = None,
) -> dict[str, str]:
    path = root / "data/exact-system-licenses.json"
    raw = path.read_bytes() if snapshot is None else snapshot[path]
    document = json.loads(raw)
    if not isinstance(document, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in document.items()
    ):
        raise SystemExit(f"{path}: expected one string-to-string JSON object")
    return document


EXACT_LICENSES = read_exact_licenses()


def exact_license(
    name: str,
    authored: str | None,
    licenses: dict[str, str] | None = None,
) -> str | None:
    expected = (EXACT_LICENSES if licenses is None else licenses).get(name)
    if expected is not None and authored != expected:
        raise SystemExit(
            f"{name}: license must be exact SPDX {expected}, found {authored!r}"
        )
    return authored


def tier1_rows(
    root: Path,
    licenses: dict[str, str],
    snapshot: dict[Path, bytes],
) -> list[dict]:
    rows = []
    content_root = root / "content/systems"
    paths = sorted(
        path
        for path in snapshot
        if path.parent == content_root
        and path.suffix == ".md"
        and path.name != "_index.md"
    )
    for path in paths:
        frontmatter = parse_frontmatter(path, snapshot[path])
        extra = frontmatter.get("extra", {})
        slug = path.stem
        rows.append(
            {
                "name": frontmatter["title"],
                "group": "systems",
                "url": f"https://ardent.tools/systems/{slug}/",
                "one_liner": frontmatter.get("description"),
                "badge": extra.get("badge"),
                "repo": extra.get("repo"),
                "license": exact_license(slug, extra.get("license"), licenses),
                "stack": extra.get("stack"),
                "private": extra.get("private", False),
            }
        )
    return rows


def ledger_rows(
    root: Path,
    licenses: dict[str, str],
    snapshot: dict[Path, bytes],
) -> list[dict]:
    path = root / "content/systems/_index.md"
    frontmatter = parse_frontmatter(path, snapshot[path])
    rows = []
    for entry in frontmatter.get("extra", {}).get("ledger", []):
        rows.append(
            {
                "name": entry["name"],
                "group": entry["group"],
                "url": None,
                "gloss": entry.get("gloss"),
                "one_liner": entry.get("one_liner"),
                "badge": entry.get("badge"),
                "repo": entry.get("repo"),
                "license": exact_license(entry["name"], entry.get("license"), licenses),
            }
        )
    return rows


def provenance(root: Path, snapshot: dict[Path, bytes]) -> dict:
    sources = []
    aggregate = hashlib.sha256()
    for path, body in snapshot.items():
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(body).hexdigest()
        sources.append({"path": relative, "sha256": digest})
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(body)
        aggregate.update(b"\0")
    return {
        "generator": "bin/generate-systems-json.py",
        "generator_version": GENERATOR_VERSION,
        "input_sha256": aggregate.hexdigest(),
        "sources": sources,
    }


def build_catalog(root: Path = ROOT) -> dict:
    snapshot = read_snapshot(root)
    licenses = read_exact_licenses(root, snapshot)
    return {
        "$schema_note": "Derived catalog. Edit the provenance sources, then run `python3 bin/site.py sync`.",
        "schema_version": SCHEMA_VERSION,
        "provenance": provenance(root, snapshot),
        "site": "https://ardent.tools",
        "catalog_url": "https://ardent.tools/systems/",
        "systems": tier1_rows(root, licenses, snapshot)
        + ledger_rows(root, licenses, snapshot),
    }


def serialize_catalog(document: dict) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def check_output(path: Path, expected: bytes, root: Path = ROOT) -> bool:
    try:
        actual = path.read_bytes()
    except OSError:
        actual = b""
    if actual == expected:
        return True
    label = display_path(path, root)
    sys.stderr.write(
        f"ERROR: stale generated artifact: {label}; run `python3 bin/site.py sync`\n"
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("static/systems.json"),
        help="destination relative to --root (defaults to static/systems.json)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the destination with a fresh derivation instead of writing",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    expected = serialize_catalog(build_catalog(root))
    if args.check:
        return 0 if check_output(output, expected, root) else 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
