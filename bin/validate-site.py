#!/usr/bin/env python3
"""Validate built XML, evidence contracts, structured data, and HTML truth."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

BASE_URL = "https://ardent.tools"
ATOM = "{http://www.w3.org/2005/Atom}"
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
FRONTMATTER = re.compile(r"^\+\+\+\n(.*?)\n\+\+\+\n", re.DOTALL)
PARITY_COMMAND = "cargo test -p logismos --test phase_3_stella_parity -- --ignored"
PARITY_MODEL = "/models/stella-1.5b-v5"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.in_json = False
        self.title = ""
        self.og_title = ""
        self.json_chunks: list[str] = []
        self._json = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and values.get("property") == "og:title":
            self.og_title = values.get("content") or ""
        if tag == "script" and values.get("type") == "application/ld+json":
            self.in_json = True
            self._json = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag == "script" and self.in_json:
            self.in_json = False
            self.json_chunks.append(self._json)

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        if self.in_json:
            self._json += data


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def frontmatter(path: Path) -> dict:
    match = FRONTMATTER.match(path.read_text())
    if not match:
        raise ValueError(f"{path}: missing TOML frontmatter")
    return tomllib.loads(match.group(1))


def route_file(output: Path, url: str) -> Path:
    path = urlparse(url).path
    if path == "/":
        return output / "index.html"
    if path.endswith("/"):
        return output / path.lstrip("/") / "index.html"
    return output / path.lstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, help="Zola build output directory")
    args = parser.parse_args()
    output = args.output.resolve()
    errors: list[str] = []

    sitemap_path = output / "sitemap.xml"
    atom_path = output / "atom.xml"
    for xml_path in (sitemap_path, atom_path):
        if not xml_path.is_file():
            fail(errors, f"missing {xml_path}")
            continue
        if not xml_path.read_bytes().startswith(b'<?xml version="1.0" encoding="UTF-8"?>'):
            fail(errors, f"{xml_path.name}: XML declaration is not byte zero")
        try:
            ET.parse(xml_path)
        except ET.ParseError as exc:
            fail(errors, f"{xml_path.name}: strict XML parse failed: {exc}")

    writing_files = sorted(p for p in Path("content/writing").glob("*.md") if p.name != "_index.md")
    expected_essays = {
        f"{BASE_URL}/writing/{path.stem}/"
        for path in writing_files
        if frontmatter(path).get("date") and not frontmatter(path).get("draft", False)
    }

    if sitemap_path.is_file():
        sitemap_root = ET.parse(sitemap_path).getroot()
        locations = [node.text or "" for node in sitemap_root.findall(f"{SITEMAP}url/{SITEMAP}loc")]
        counts = Counter(locations)
        for location, count in counts.items():
            if count != 1:
                fail(errors, f"sitemap: {location} appears {count} times")
            target = route_file(output, location)
            if not target.is_file():
                fail(errors, f"sitemap: {location} does not resolve to {target}")
        for essay in expected_essays:
            if counts[essay] != 1:
                fail(errors, f"sitemap: dated essay {essay} appears {counts[essay]} times")

    if atom_path.is_file():
        atom_root = ET.parse(atom_path).getroot()
        ids = [node.text or "" for node in atom_root.findall(f"{ATOM}entry/{ATOM}id")]
        counts = Counter(ids)
        if len(ids) != len(expected_essays):
            fail(errors, f"atom: expected {len(expected_essays)} entries, found {len(ids)}")
        for essay in expected_essays:
            if counts[essay] != 1:
                fail(errors, f"atom: dated essay {essay} appears {counts[essay]} times")

    systems = sorted(p for p in Path("content/systems").glob("*.md") if p.name != "_index.md")
    expected_system_urls = {f"{BASE_URL}/systems/{path.stem}/" for path in systems}
    casts: list[tuple[Path, str]] = []
    for path in systems:
        demo = frontmatter(path).get("extra", {}).get("demo", {})
        if demo.get("cast"):
            casts.append((path, demo["cast"]))

    html_files = sorted(output.rglob("*.html"))
    html = {path: path.read_text() for path in html_files}
    asset_pattern = re.compile(r"(?:href|src)=[\"'][^\"']*/vendor/asciinema/asciinema-player", re.I)
    headers = Path("_headers").read_text()
    player_requests = [str(path) for path, text in html.items() if asset_pattern.search(text)]
    data_casts = [str(path) for path, text in html.items() if "data-cast=" in text]

    if not casts:
        if player_requests:
            fail(errors, f"zero casts but player assets are requested by: {player_requests}")
        if data_casts:
            fail(errors, f"zero casts but data-cast markup exists in: {data_casts}")
        if "wasm-unsafe-eval" in headers:
            fail(errors, "zero casts but _headers still permits wasm-unsafe-eval")
        if any("WATCH RECORDING" in text for text in html.values()):
            fail(errors, "zero casts but built catalog exposes WATCH RECORDING")
    else:
        if "wasm-unsafe-eval" not in headers:
            fail(errors, "published casts require an explicit wasm-unsafe-eval CSP disposition")
        for source, cast in casts:
            cast_file = Path("static") / cast.lstrip("/")
            if not cast_file.is_file():
                fail(errors, f"{source}: cast points to missing {cast_file}")

    index_path = output / "index.html"
    if index_path.is_file():
        page_parser = PageParser()
        page_parser.feed(index_path.read_text())
        person_nodes: list[dict] = []
        for chunk in page_parser.json_chunks:
            try:
                node = json.loads(chunk)
            except json.JSONDecodeError as exc:
                fail(errors, f"index JSON-LD does not parse: {exc}")
                continue
            if node.get("@type") == "Person":
                person_nodes.append(node)
        if len(person_nodes) != 1:
            fail(errors, f"expected one Person JSON-LD node, found {len(person_nodes)}")
        else:
            internal = {url for url in person_nodes[0].get("knowsAbout", []) if url.startswith(BASE_URL)}
            if internal != expected_system_urls:
                fail(errors, f"Person knowsAbout internal URLs differ: {sorted(internal ^ expected_system_urls)}")
            for url in internal:
                if not route_file(output, url).is_file():
                    fail(errors, f"Person knowsAbout URL does not resolve: {url}")

    apostrophe_path = output / "writing/coordination-that-isnt-voting/index.html"
    if apostrophe_path.is_file():
        apostrophe_parser = PageParser()
        raw = apostrophe_path.read_text()
        apostrophe_parser.feed(raw)
        expected_title = "Coordination that isn't voting - Ardent Tools"
        if apostrophe_parser.title != expected_title:
            fail(errors, f"document title mismatch: {apostrophe_parser.title!r}")
        if apostrophe_parser.og_title != expected_title:
            fail(errors, f"og:title mismatch: {apostrophe_parser.og_title!r}")
        if "&amp;#" in raw:
            fail(errors, "apostrophe page contains a double-escaped HTML entity")

    parity_sources = [Path("content/systems/logismos.md"), Path("static/tapes/logismos-parity.tape")]
    for path in parity_sources:
        text = path.read_text()
        if PARITY_COMMAND not in text:
            fail(errors, f"{path}: missing exact ignored-test command")
        if PARITY_MODEL not in text:
            fail(errors, f"{path}: missing Stella model prerequisite")
    tape = Path("static/tapes/logismos-parity.tape").read_text()
    if "1 passed" not in tape:
        fail(errors, "Logismos tape does not reject a zero-test green exit")

    source_corpus = "\n".join(
        path.read_text()
        for path in [Path("config.toml"), Path("static/llms.txt"), Path("static/img/og-card.svg")]
    )
    for stale_claim in ("Recordings and receipts, not claims", "Every recording on one page"):
        if stale_claim in source_corpus:
            fail(errors, f"stale recording claim remains: {stale_claim!r}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "pass",
                "html_routes": len(html_files),
                "dated_essays": len(expected_essays),
                "published_casts": len(casts),
                "person_system_urls": len(expected_system_urls),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
