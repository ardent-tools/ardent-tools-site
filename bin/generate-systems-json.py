#!/usr/bin/env python3
# bin/generate-systems-json.py — stdlib only (tomllib, re, json; Python
# 3.11+, already on the CI runner for typikon-validate's jsonschema
# step). Reads the same TOML frontmatter systems.html/catalog-ledger.html
# render; writes static/systems.json for zola build to copy through.
# Run before `zola build` in the deploy workflow, same stage as the
# og-card PNG render (DESIGN-v1.1 T3).
#
# WHY: derive-over-declare — one source of truth (content/systems/*.md
# frontmatter), two renderings (the HTML catalog, this JSON file). Never
# hand-edit static/systems.json; it is overwritten on every run.

import argparse
import json
import re
import tomllib
from pathlib import Path

CONTENT = Path("content/systems")
FRONTMATTER = re.compile(r"^\+\+\+\n(.*?)\n\+\+\+\n", re.DOTALL)


def read_frontmatter(path: Path) -> dict:
    m = FRONTMATTER.match(path.read_text())
    if not m:
        raise SystemExit(f"{path}: no +++ frontmatter block")
    return tomllib.loads(m.group(1))


def tier1_rows() -> list[dict]:
    rows = []
    for f in sorted(CONTENT.glob("*.md")):
        if f.name == "_index.md":
            continue
        fm = read_frontmatter(f)
        extra = fm.get("extra", {})
        slug = f.stem
        rows.append({
            "name": fm["title"],
            "group": "systems",
            "url": f"https://ardent.tools/systems/{slug}/",
            "one_liner": fm.get("description"),
            "badge": extra.get("badge"),
            "repo": extra.get("repo"),
            "license": extra.get("license"),  # None until DESIGN-v1.3 §4 item 6 lands
            "stack": extra.get("stack"),
            "private": extra.get("private", False),
        })
    return rows


def ledger_rows() -> list[dict]:
    fm = read_frontmatter(CONTENT / "_index.md")
    rows = []
    for entry in fm.get("extra", {}).get("ledger", []):
        rows.append({
            "name": entry["name"],
            "group": entry["group"],
            "url": None,  # tier 2/3 has no dedicated page; repo is primary
            "gloss": entry.get("gloss"),
            "one_liner": entry.get("one_liner"),
            "badge": entry.get("badge"),
            "repo": entry.get("repo"),
            "license": entry.get("license"),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("static/systems.json"),
        help="destination (defaults to static/systems.json)",
    )
    args = parser.parse_args()
    out = {
        "$schema_note": "Generated from content/systems/*.md — do not hand-edit.",
        "site": "https://ardent.tools",
        "catalog_url": "https://ardent.tools/systems/",
        "systems": tier1_rows() + ledger_rows(),
    }
    args.output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
