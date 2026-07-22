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
TEST_ATTRIBUTE_COMMAND = "rg -o '#\\[(tokio::)?test' --glob '*.rs' | wc -l"
WORKSPACE_COMMAND = "cargo metadata --no-deps --format-version 1 | jq '.workspace_members | length'"
TOKEI_COMMAND = "tokei -o json . | jq '.Rust | {code, comments, blanks, physical: (.code + .comments + .blanks)}'"
PINNED_SNAPSHOTS = {
    "akroasis.md": "4e3712669df7",
    "hamma.md": "216e2adc83d5",
    "logismos.md": "94e4e97dce6e",
    "thumos.md": "77cc89906a52",
}


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
        evidence_url = f"{BASE_URL}/evidence/"
        demos_url = f"{BASE_URL}/demos/"
        if counts[evidence_url] != 1:
            fail(errors, f"sitemap: canonical evidence route appears {counts[evidence_url]} times")
        if counts[demos_url] != 0:
            fail(errors, "sitemap advertises compatibility-only /demos/")

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
        source = path.read_text()
        demo = frontmatter(path).get("extra", {}).get("demo", {})
        if demo.get("cast"):
            casts.append((path, demo["cast"]))
        if "| Claim | Method |" in source:
            fail(errors, f"{path}: measurement table must say Reproduction method")
        required_revision = PINNED_SNAPSHOTS.get(path.name)
        for line_number, line in enumerate(source.splitlines(), start=1):
            is_claim_row = line.startswith("|")
            if is_claim_row and "test-attribute occurrences" in line and f"`{TEST_ATTRIBUTE_COMMAND}`" not in line:
                fail(errors, f"{path}:{line_number}: test-attribute count lacks the exact reproduction command")
            if is_claim_row and "Cargo workspace member" in line and f"`{WORKSPACE_COMMAND}`" not in line:
                fail(errors, f"{path}:{line_number}: workspace count lacks the exact reproduction command")
            if is_claim_row and "Rust code lines" in line and f"`{TOKEI_COMMAND}`" not in line:
                fail(errors, f"{path}:{line_number}: Rust line count lacks the exact reproduction command")
            if is_claim_row and required_revision and any(
                marker in line
                for marker in ("Rust code lines", "Cargo workspace member", "test-attribute occurrences")
            ) and required_revision not in line:
                fail(errors, f"{path}:{line_number}: snapshot claim lacks revision {required_revision}")

    akroasis = Path("content/systems/akroasis.md").read_text()
    if "23,569 Rust code lines; 24,538 Rust code-plus-comment lines" not in akroasis:
        fail(errors, "Akroasis line claim must remain 23,569 code and 24,538 code-plus-comment")
    if re.search(r"24,538[^\n|]*physical", akroasis, re.I):
        fail(errors, "Akroasis must not label 24,538 as physical lines")

    html_files = sorted(output.rglob("*.html"))
    html = {path: path.read_text() for path in html_files}
    asset_pattern = re.compile(r"(?:href|src)=[\"'][^\"']*/vendor/asciinema/asciinema-player", re.I)
    headers = Path("_headers").read_text()
    player_requests = [str(path) for path, text in html.items() if asset_pattern.search(text)]
    data_casts = [str(path) for path, text in html.items() if "data-cast=" in text]

    evidence_path = output / "evidence/index.html"
    demos_path = output / "demos/index.html"
    if not evidence_path.is_file():
        fail(errors, "canonical /evidence/ page is missing")
    else:
        evidence_html = evidence_path.read_text()
        if 'href="https://ardent.tools/evidence/"' not in evidence_html:
            fail(errors, "/evidence/ does not publish its canonical URL")
    if demos_path.exists():
        fail(errors, "compatibility-only /demos/ was generated as a canonical page")

    redirect_lines = {
        line.strip()
        for line in Path("_redirects").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    for declaration in ("/demos /evidence/ 301", "/demos/* /evidence/ 301"):
        if declaration not in redirect_lines:
            fail(errors, f"_redirects: missing permanent compatibility declaration {declaration!r}")

    if not re.search(r"^\s*Cache-Control:\s*[^\n]*\bno-transform\b", headers, re.MULTILINE | re.I):
        fail(errors, "_headers: root HTML policy must include Cache-Control no-transform")

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

    thumos_tape = Path("static/tapes/thumos-boot.tape").read_text()
    for required in (
        'Type "cd crates/thumos"',
        "cargo build --release --target armv7a-none-eabi --features qemu --jobs 8",
        "../../scripts/qemu-runner.sh target/armv7a-none-eabi/release/thumos",
    ):
        if required not in thumos_tape:
            fail(errors, f"Thumos tape lacks authoritative CI command/path: {required}")
    if "scripts/qemu-runner.sh target/" in thumos_tape.replace("../../scripts/qemu-runner.sh target/", ""):
        fail(errors, "Thumos tape retains the stale repo-root runner path")

    kanon_tape = Path("static/tapes/kanon-gate.tape").read_text()
    for required in (
        "mktemp -d -t kanon-gate-tape.XXXXXX",
        "trap cleanup_kanon_tape EXIT",
        "switch --detach 1a0ee8a29cb2",
        "status --porcelain",
        "six featured repos carry Kanon config; enforcement is repository-specific",
    ):
        if required not in kanon_tape:
            fail(errors, f"Kanon tape lacks disposable-clone contract: {required}")
    seed_at = kanon_tape.find("echo '// TODO fix this later'")
    clean_at = kanon_tape.find("status --porcelain")
    if clean_at < 0 or seed_at < 0 or clean_at > seed_at:
        fail(errors, "Kanon tape must assert clone cleanliness before seeding")
    for dangerous in ("git checkout --", "git reset", "$HOME/dev", "every public repo"):
        if dangerous in kanon_tape:
            fail(errors, f"Kanon tape retains dangerous or stale form: {dangerous!r}")

    harmonia_tape = Path("static/tapes/harmonia-serve.tape").read_text()
    if "metadata resolution and curation stay named as open" in harmonia_tape:
        fail(errors, "Harmonia tape retains the stale adapter limitation")
    if "no external-provider credentials" not in harmonia_tape:
        fail(errors, "Harmonia tape lacks its seeded/no-provider-credential limitation")

    source_corpus = "\n".join(
        path.read_text()
        for path in [
            Path("config.toml"),
            Path("content/colophon.md"),
            Path("static/llms.txt"),
            Path("static/img/og-card.svg"),
        ]
    )
    for stale_claim in ("Recordings and receipts, not claims", "Every recording on one page"):
        if stale_claim in source_corpus:
            fail(errors, f"stale recording claim remains: {stale_claim!r}")
    for stale_claim in (
        "third-party application dependencies",
        "No third-party application requests",
        "Every push runs",
    ):
        if stale_claim in source_corpus:
            fail(errors, f"stale dependency or trigger claim remains: {stale_claim!r}")

    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    sys.stdout.write(
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
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
