#!/usr/bin/env python3
"""Validate built XML, evidence contracts, structured data, and HTML truth."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlparse

from career_claim_contract import FORBIDDEN_PUBLIC_VARIANTS
from release_manifest import (
    read_contract,
    validate_manifest,
    validate_public_references,
)
from header_contract import load_headers
from html_authority import AUTHORITY_NAME, validate_authority
from pages_runtime import validate_runtime
from redirect_contract import load_redirects

BASE_URL = "https://ardent.tools"
ATOM = "{http://www.w3.org/2005/Atom}"
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
FRONTMATTER = re.compile(r"^\+\+\+\n(.*?)\n\+\+\+\n", re.DOTALL)
PARITY_COMMAND = "cargo test -p logismos --test phase_3_stella_parity -- --ignored"
PARITY_MODEL = "/models/stella-1.5b-v5"
TEST_ATTRIBUTE_COMMAND = "rg -o '#\\[(tokio::)?test' --glob '*.rs' | wc -l"
WORKSPACE_COMMAND = (
    "cargo metadata --no-deps --format-version 1 | jq '.workspace_members | length'"
)
TOKEI_COMMAND = "tokei -o json . | jq '.Rust | {code, comments, blanks, physical: (.code + .comments + .blanks)}'"
PINNED_SNAPSHOTS = {
    "akroasis.md": "4e3712669df7",
    "hamma.md": "216e2adc83d5",
    "logismos.md": "94e4e97dce6e",
    "thumos.md": "77cc89906a52",
}
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
ASSET_HASH_RE = re.compile(r"^[0-9a-f]{20}$")
ASSET_EPOCH_RE = re.compile(r"^[1-9][0-9]*$")
TAPE_TARGETS = {
    "aletheia-health.tape": "ARDENT_ALETHEIA_ROOT",
    "hamma-tests.tape": "ARDENT_HAMMA_ROOT",
    "harmonia-serve.tape": "ARDENT_HARMONIA_ROOT",
    "logismos-parity.tape": "ARDENT_LOGISMOS_ROOT",
    "thumos-boot.tape": "ARDENT_THUMOS_ROOT",
}
FORBIDDEN_TAPE_FORMS = (
    "sudo ",
    "apt-get ",
    "dnf install",
    "brew install",
    "ollama pull",
    "demo/instance serve &",
    "demo/instance tui",
)


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


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and "src" in values:
            self.references.append(("JavaScript", values.get("src") or ""))
        if tag == "link" and "stylesheet" in (values.get("rel") or "").lower().split():
            self.references.append(("CSS", values.get("href") or ""))


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


def parse_cloudflare_headers(
    text: str,
) -> list[tuple[str, list[tuple[str, str | None]]]]:
    """Parse the subset of Pages _headers syntax used by this site."""
    rules: list[tuple[str, list[tuple[str, str | None]]]] = []
    current: list[tuple[str, str | None]] | None = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw[0].isspace():
            current = []
            rules.append((stripped, current))
            continue
        if current is None:
            raise ValueError(f"header without path rule: {stripped}")
        if stripped.startswith("! "):
            current.append((stripped[2:].strip().lower(), None))
            continue
        if ":" not in stripped:
            raise ValueError(f"malformed header declaration: {stripped}")
        name, value = stripped.split(":", 1)
        current.append((name.strip().lower(), value.strip()))
    return rules


def effective_headers(
    path: str, rules: list[tuple[str, list[tuple[str, str | None]]]]
) -> dict[str, list[str]]:
    """Apply Cloudflare's inherited, comma-joined overlap semantics."""
    effective: dict[str, list[str]] = {}
    for pattern, operations in rules:
        if not fnmatch.fnmatchcase(path, pattern):
            continue
        for name, value in operations:
            if value is None:
                effective.pop(name, None)
            else:
                effective.setdefault(name, []).append(value)
    return effective


def output_url(output: Path, path: Path) -> str:
    relative = path.relative_to(output).as_posix()
    if relative == "index.html":
        return "/"
    if relative.endswith("/index.html"):
        return f"/{relative[:-10]}"
    return f"/{relative}"


def validate_cache_contract(errors: list[str], output: Path, headers_text: str) -> None:
    try:
        rules = parse_cloudflare_headers(headers_text)
    except ValueError as exc:
        fail(errors, f"_headers: {exc}")
        return

    paths = {
        output_url(output, path)
        for path in output.rglob("*")
        if path.is_file()
        and path.name not in {"_headers", "_redirects", "_routes.json"}
    }
    for pattern, _ in rules:
        paths.add(pattern.replace("*", "contract-probe.bin"))

    for path in sorted(paths):
        cache_values = effective_headers(path, rules).get("cache-control", [])
        if len(cache_values) != 1:
            fail(
                errors,
                f"_headers: {path} has {len(cache_values)} effective Cache-Control values: {cache_values}",
            )
            continue
        directives: list[tuple[str, str | None]] = []
        for raw in cache_values[0].split(","):
            name, separator, value = raw.strip().partition("=")
            directives.append(
                (
                    name.strip().lower(),
                    value.strip().strip('"').lower() if separator else None,
                )
            )
        if Counter(directives) != Counter(
            {("no-store", None): 1, ("no-transform", None): 1}
        ):
            fail(
                errors,
                f"_headers: {path} Cache-Control must be exactly no-store, no-transform; "
                f"found {cache_values[0]!r}",
            )


def inspect_asset_reference(
    errors: list[str],
    *,
    page: Path,
    kind: str,
    reference: str,
    output: Path,
    asset_epoch: str,
) -> tuple[str, str] | None:
    try:
        resolved = urljoin(BASE_URL + "/", reference)
        parsed = urlparse(resolved)
    except ValueError:
        fail(errors, f"{page}: malformed {kind} asset URL: {reference!r}")
        return None
    base = urlparse(BASE_URL)
    if (parsed.scheme.lower(), parsed.netloc.lower()) != (
        base.scheme.lower(),
        base.netloc.lower(),
    ):
        fail(errors, f"{page}: external {kind} asset is not allowed: {reference!r}")
        return None
    if parsed.fragment:
        fail(
            errors, f"{page}: {kind} asset URL must not carry a fragment: {reference!r}"
        )
        return None
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    names = [name for name, _ in pairs]
    if len(pairs) != 2 or Counter(names) != Counter({"h": 1, "v": 1}):
        fail(
            errors,
            f"{page}: {kind} asset must carry exactly one h and one v query and no others: "
            f"{reference!r}",
        )
        return None
    values = dict(pairs)
    authored_hash = values["h"]
    if not ASSET_HASH_RE.fullmatch(authored_hash):
        fail(
            errors,
            f"{page}: {kind} asset has malformed h={authored_hash!r}: {reference!r}",
        )
        return None
    if values["v"] != asset_epoch:
        fail(
            errors,
            f"{page}: {kind} asset has v={values['v']!r}, expected {asset_epoch!r}: {reference!r}",
        )
        return None
    asset_path = output / parsed.path.lstrip("/")
    if not asset_path.is_file():
        fail(errors, f"{page}: {kind} asset does not resolve in output: {parsed.path}")
        return None
    digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    if not digest.startswith(authored_hash):
        fail(
            errors,
            f"{page}: {kind} asset digest mismatch for {reference!r}: "
            f"h={authored_hash}, SHA-256={digest}",
        )
    return parsed.path, authored_hash


def validate_asset_contract(
    errors: list[str], html: dict[Path, str], output: Path, asset_epoch: str
) -> None:
    identities: dict[str, tuple[str, Path]] = {}
    for page, text in html.items():
        parser = AssetParser()
        parser.feed(text)
        kinds = {kind for kind, _ in parser.references}
        for required in ("CSS", "JavaScript"):
            if required not in kinds:
                fail(errors, f"{page}: no authored {required} asset reference found")
        for kind, reference in parser.references:
            inspected = inspect_asset_reference(
                errors,
                page=page,
                kind=kind,
                reference=reference,
                output=output,
                asset_epoch=asset_epoch,
            )
            if inspected is None:
                continue
            asset_path, authored_hash = inspected
            prior = identities.get(asset_path)
            if prior and prior[0] != authored_hash:
                fail(
                    errors,
                    f"conflicting authored hashes for {asset_path}: {prior[0]} at {prior[1]}, "
                    f"{authored_hash} at {page}",
                )
            else:
                identities[asset_path] = (authored_hash, page)


def validate_revision(
    errors: list[str], output: Path, expected_revision: str | None
) -> None:
    path = output / "build-revision.txt"
    if not path.is_file():
        fail(errors, "missing build-revision.txt")
        return
    raw = path.read_bytes()
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError:
        fail(errors, "build-revision.txt is not ASCII")
        return
    if not value.endswith("\n") or value.count("\n") != 1:
        fail(errors, "build-revision.txt must contain one revision plus one newline")
        return
    revision = value[:-1]
    if not REVISION_RE.fullmatch(revision):
        fail(errors, "build-revision.txt is not exactly one lowercase 40-hex revision")
    if expected_revision is not None and revision != expected_revision:
        fail(
            errors,
            f"build-revision.txt mismatch: expected {expected_revision}, found {revision}",
        )


def validate_tape_contract(errors: list[str], path: Path) -> None:
    text = path.read_text()
    expected_run = f"vhs static/tapes/{path.name}"
    if "Run from the ardent-tools-site root" not in text or expected_run not in text:
        fail(errors, f"{path}: instructions must run {expected_run} from the site root")
    for forbidden in FORBIDDEN_TAPE_FORMS:
        if forbidden in text:
            fail(errors, f"{path}: forbidden recording behavior remains: {forbidden!r}")

    target_env = TAPE_TARGETS.get(path.name)
    if target_env:
        if target_env not in text:
            fail(
                errors,
                f"{path}: missing explicit target checkout variable {target_env}",
            )
        if f'test -n \\"${target_env}\\"' not in text:
            fail(
                errors, f"{path}: target checkout variable {target_env} is not asserted"
            )
        if f'cd \\"${target_env}' not in text:
            fail(errors, f"{path}: recorded terminal never enters {target_env}")

    type_lines = [line for line in text.splitlines() if line.startswith('Type "')]
    for line in type_lines:
        if re.search(r"\s&(?:[;\"]|$)", line) and "$!" not in line:
            fail(errors, f"{path}: unmanaged background process: {line}")

    waits = re.findall(r"^Wait\+Screen /([^/]+)/$", text, re.MULTILINE)
    if not waits:
        fail(errors, f"{path}: no output-observation sentinel")
    for token in waits:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]+_OK", token):
            fail(
                errors,
                f"{path}: Wait+Screen must observe a unique success token, got {token!r}",
            )
        if any(token in line for line in type_lines):
            fail(
                errors, f"{path}: awaited token {token!r} is visible in a typed command"
            )

    if path.name in {"aletheia-health.tape", "harmonia-serve.tape"}:
        for required in ("mktemp -d", "trap ", "SERVER_PID", "kill -0", "curl -sf"):
            if required not in text:
                fail(errors, f"{path}: stateful service plan lacks {required!r}")


def validate_player_contract(
    errors: list[str],
    casts: list[tuple[Path, str]],
    html: dict[Path, str],
    headers: str,
    output: Path,
    static_root: Path = Path("static"),
    asset_epoch: str = "INVALID",
) -> None:
    asset_pattern = re.compile(
        r"(?:href|src)=[\"'][^\"']*/vendor/asciinema/asciinema-player", re.I
    )
    player_requests = [
        str(path) for path, text in html.items() if asset_pattern.search(text)
    ]
    data_casts = [str(path) for path, text in html.items() if "data-cast=" in text]
    if not casts:
        if player_requests:
            fail(
                errors,
                f"zero casts but player assets are requested by: {player_requests}",
            )
        if data_casts:
            fail(errors, f"zero casts but data-cast markup exists in: {data_casts}")
        if "wasm-unsafe-eval" in headers:
            fail(errors, "zero casts but _headers still permits wasm-unsafe-eval")
        if any("WATCH RECORDING" in text for text in html.values()):
            fail(errors, "zero casts but built catalog exposes WATCH RECORDING")
        return

    if "wasm-unsafe-eval" not in headers:
        fail(
            errors,
            "published casts require an explicit wasm-unsafe-eval CSP disposition",
        )
    catalog = html.get(output / "systems/index.html", "")
    evidence = html.get(output / "evidence/index.html", "")
    for source, cast in casts:
        cast_file = static_root / cast.lstrip("/")
        if not cast_file.is_file():
            fail(errors, f"{source}: cast points to missing {cast_file}")
            continue
        page_path = output / "systems" / source.stem / "index.html"
        page_html = html.get(page_path, "")
        cast_hash = hashlib.sha256(cast_file.read_bytes()).hexdigest()[:20]
        cast_url = f"{BASE_URL}{cast}?h={cast_hash}&amp;v={asset_epoch}"
        marker = f'data-cast="{cast_url}"'
        corpus_count = sum(text.count(marker) for text in html.values())
        if corpus_count != 1:
            fail(
                errors,
                f"{source}: expected exactly one rendered data-cast, found {corpus_count}",
            )
        if page_html.count(marker) != 1:
            fail(errors, f"{source}: system page must render exactly one data-cast")
        if (
            page_html.count("asciinema-player.css") != 1
            or page_html.count("asciinema-player.min.js") != 1
        ):
            fail(
                errors,
                f"{source}: system page lacks exactly one conditional player CSS/JS pair",
            )
        system_href = f'href="{BASE_URL}/systems/{source.stem}/"'
        relative_href = f'href="/systems/{source.stem}/"'
        if "WATCH RECORDING" not in catalog or not (
            system_href in catalog or relative_href in catalog
        ):
            fail(errors, f"{source}: systems catalog lacks a visible recording link")
        if not (system_href in evidence or relative_href in evidence):
            fail(errors, f"{source}: evidence register lacks a visible recording link")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, help="Zola build output directory")
    parser.add_argument("--expected-revision")
    args = parser.parse_args()
    if args.expected_revision is not None and not REVISION_RE.fullmatch(
        args.expected_revision
    ):
        parser.error(
            "--expected-revision must be exactly one lowercase 40-hex revision"
        )
    output = args.output.resolve()
    errors: list[str] = []
    headers_path = output / "_headers"
    try:
        headers = headers_path.read_text()
    except OSError as exc:
        fail(errors, f"_headers: cannot read retained control file: {exc}")
        headers = ""
    config = tomllib.loads(Path("config.toml").read_text())
    asset_epoch = config.get("extra", {}).get("asset_epoch")
    if not isinstance(asset_epoch, str) or not ASSET_EPOCH_RE.fullmatch(asset_epoch):
        fail(errors, "config.toml: extra.asset_epoch must be a nonzero decimal string")
        asset_epoch = "INVALID"

    validate_revision(errors, output, args.expected_revision)
    validate_cache_contract(errors, output, headers)

    contract, contract_errors = read_contract()
    errors.extend(contract_errors)
    sentinel = output / "build-revision.txt"
    release_revision = args.expected_revision
    if release_revision is None and sentinel.is_file():
        candidate = sentinel.read_text(errors="replace").removesuffix("\n")
        if REVISION_RE.fullmatch(candidate):
            release_revision = candidate
    release_manifest: dict = {}
    if contract and release_revision is not None:
        manifest_path = output / contract["manifest_name"]
        if not manifest_path.is_file():
            fail(errors, f"missing {contract['manifest_name']}")
        else:
            release_manifest, manifest_errors = validate_manifest(
                manifest_path.read_bytes(),
                output=output,
                expected_revision=release_revision,
                expected_epoch=asset_epoch,
                contract=contract,
            )
            errors.extend(manifest_errors)
            errors.extend(validate_public_references(output, release_manifest))
            authority_path = output / AUTHORITY_NAME
            if not authority_path.is_file():
                fail(errors, f"missing {AUTHORITY_NAME}")
            else:
                _, authority_errors = validate_authority(
                    authority_path.read_bytes(),
                    output=output,
                    expected_revision=release_revision,
                    base_url=BASE_URL,
                )
                errors.extend(authority_errors)
            _, header_errors = load_headers(headers_path, release_manifest)
            errors.extend(header_errors)
    elif release_revision is None:
        fail(errors, "cannot validate release manifest without a valid build revision")

    sitemap_path = output / "sitemap.xml"
    atom_path = output / "atom.xml"
    for xml_path in (sitemap_path, atom_path):
        if not xml_path.is_file():
            fail(errors, f"missing {xml_path}")
            continue
        if not xml_path.read_bytes().startswith(
            b'<?xml version="1.0" encoding="UTF-8"?>'
        ):
            fail(errors, f"{xml_path.name}: XML declaration is not byte zero")
        try:
            ET.parse(xml_path)
        except ET.ParseError as exc:
            fail(errors, f"{xml_path.name}: strict XML parse failed: {exc}")

    writing_files = sorted(
        p for p in Path("content/writing").glob("*.md") if p.name != "_index.md"
    )
    expected_essays = {
        f"{BASE_URL}/writing/{path.stem}/"
        for path in writing_files
        if frontmatter(path).get("date") and not frontmatter(path).get("draft", False)
    }

    if sitemap_path.is_file():
        sitemap_root = ET.parse(sitemap_path).getroot()
        locations = [
            node.text or ""
            for node in sitemap_root.findall(f"{SITEMAP}url/{SITEMAP}loc")
        ]
        counts = Counter(locations)
        for location, count in counts.items():
            if count != 1:
                fail(errors, f"sitemap: {location} appears {count} times")
            target = route_file(output, location)
            if not target.is_file():
                fail(errors, f"sitemap: {location} does not resolve to {target}")
        for essay in expected_essays:
            if counts[essay] != 1:
                fail(
                    errors,
                    f"sitemap: dated essay {essay} appears {counts[essay]} times",
                )
        evidence_url = f"{BASE_URL}/evidence/"
        demos_url = f"{BASE_URL}/demos/"
        if counts[evidence_url] != 1:
            fail(
                errors,
                f"sitemap: canonical evidence route appears {counts[evidence_url]} times",
            )
        if counts[demos_url] != 0:
            fail(errors, "sitemap advertises compatibility-only /demos/")

    if atom_path.is_file():
        atom_root = ET.parse(atom_path).getroot()
        ids = [node.text or "" for node in atom_root.findall(f"{ATOM}entry/{ATOM}id")]
        counts = Counter(ids)
        if len(ids) != len(expected_essays):
            fail(
                errors,
                f"atom: expected {len(expected_essays)} entries, found {len(ids)}",
            )
        for essay in expected_essays:
            if counts[essay] != 1:
                fail(errors, f"atom: dated essay {essay} appears {counts[essay]} times")

    systems = sorted(
        p for p in Path("content/systems").glob("*.md") if p.name != "_index.md"
    )
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
            if (
                is_claim_row
                and "test-attribute occurrences" in line
                and f"`{TEST_ATTRIBUTE_COMMAND}`" not in line
            ):
                fail(
                    errors,
                    f"{path}:{line_number}: test-attribute count lacks the exact reproduction command",
                )
            if (
                is_claim_row
                and "Cargo workspace member" in line
                and f"`{WORKSPACE_COMMAND}`" not in line
            ):
                fail(
                    errors,
                    f"{path}:{line_number}: workspace count lacks the exact reproduction command",
                )
            if (
                is_claim_row
                and "Rust code lines" in line
                and f"`{TOKEI_COMMAND}`" not in line
            ):
                fail(
                    errors,
                    f"{path}:{line_number}: Rust line count lacks the exact reproduction command",
                )
            if (
                is_claim_row
                and required_revision
                and any(
                    marker in line
                    for marker in (
                        "Rust code lines",
                        "Cargo workspace member",
                        "test-attribute occurrences",
                    )
                )
                and required_revision not in line
            ):
                fail(
                    errors,
                    f"{path}:{line_number}: snapshot claim lacks revision {required_revision}",
                )

    exact_licenses = json.loads(Path("data/exact-system-licenses.json").read_text())
    ledger = (
        frontmatter(Path("content/systems/_index.md"))
        .get("extra", {})
        .get("ledger", [])
    )
    ledger_licenses = {entry["name"]: entry.get("license") for entry in ledger}
    for name, expected in exact_licenses.items():
        if name == "akroasis":
            continue
        if ledger_licenses.get(name) != expected:
            fail(
                errors,
                f"content/systems/_index.md: {name} license must be exact SPDX {expected}",
            )
    akroasis_extra = frontmatter(Path("content/systems/akroasis.md")).get("extra", {})
    if akroasis_extra.get("license") != exact_licenses.get("akroasis"):
        fail(
            errors,
            "content/systems/akroasis.md: license differs from canonical mapping",
        )

    akroasis = Path("content/systems/akroasis.md").read_text()
    if "23,569 Rust code lines; 24,538 Rust code-plus-comment lines" not in akroasis:
        fail(
            errors,
            "Akroasis line claim must remain 23,569 code and 24,538 code-plus-comment",
        )
    if re.search(r"24,538[^\n|]*physical", akroasis, re.I):
        fail(errors, "Akroasis must not label 24,538 as physical lines")

    html_files = sorted(output.rglob("*.html"))
    html = {path: path.read_text() for path in html_files}
    validate_asset_contract(errors, html, output, asset_epoch)
    validate_player_contract(
        errors, casts, html, headers, output, asset_epoch=asset_epoch
    )

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

    _, redirect_errors = load_redirects(output / "_redirects")
    for error in redirect_errors:
        fail(errors, error)

    for error in validate_runtime(output):
        fail(errors, error)

    if not re.search(
        r"^\s*Cache-Control:\s*[^\n]*\bno-transform\b", headers, re.MULTILINE | re.I
    ):
        fail(
            errors, "_headers: root HTML policy must include Cache-Control no-transform"
        )

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
            internal = {
                url
                for url in person_nodes[0].get("knowsAbout", [])
                if url.startswith(BASE_URL)
            }
            if internal != expected_system_urls:
                fail(
                    errors,
                    f"Person knowsAbout internal URLs differ: {sorted(internal ^ expected_system_urls)}",
                )
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

    parity_sources = [
        Path("content/systems/logismos.md"),
        Path("static/tapes/logismos-parity.tape"),
    ]
    for path in parity_sources:
        text = path.read_text()
        if PARITY_COMMAND not in text:
            fail(errors, f"{path}: missing exact ignored-test command")
        if PARITY_MODEL not in text:
            fail(errors, f"{path}: missing Stella model prerequisite")
    for tape_path in sorted(Path("static/tapes").glob("*.tape")):
        validate_tape_contract(errors, tape_path)

    tape = Path("static/tapes/logismos-parity.tape").read_text()
    if "1 passed" not in tape:
        fail(errors, "Logismos tape does not reject a zero-test green exit")
    if "phases/03-stella/golden/embeddings_dim1024.safetensors" not in tape:
        fail(errors, "Logismos tape lacks the actual safetensors parity fixture")
    if "cpu_baseline.json" in tape:
        fail(errors, "Logismos tape retains the wrong cpu_baseline.json fixture")

    thumos_tape = Path("static/tapes/thumos-boot.tape").read_text()
    for required in (
        'Type "cd \\"$ARDENT_THUMOS_ROOT/crates/thumos\\""',
        "cargo build --release --target armv7a-none-eabi --features qemu --jobs 8",
        "../../scripts/qemu-runner.sh target/armv7a-none-eabi/release/thumos",
    ):
        if required not in thumos_tape:
            fail(errors, f"Thumos tape lacks authoritative CI command/path: {required}")
    if "scripts/qemu-runner.sh target/" in thumos_tape.replace(
        "../../scripts/qemu-runner.sh target/", ""
    ):
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
    seed_at = kanon_tape.find("kanon_recording_proof = [")
    clean_assertions = [
        match.start() for match in re.finditer(r"status --porcelain", kanon_tape)
    ]
    if seed_at < 0 or len(clean_assertions) != 1 or clean_assertions[0] > seed_at:
        fail(
            errors,
            "Kanon tape must contain exactly one clean-tree assertion before seeding",
        )
    initial_lint_at = kanon_tape.find(
        'kanon lint \\"$PROOF_FILE\\"; rc=$?; test \\"$rc\\" -eq 1', seed_at
    )
    initial_result_at = kanon_tape.find(
        "Wait+Screen /KANON_VIOLATION_OK/", initial_lint_at
    )
    fix_at = kanon_tape.find('kanon lint --fix \\"$PROOF_FILE\\"', initial_result_at)
    post_fix_lint_at = kanon_tape.find('kanon lint \\"$PROOF_FILE\\"', fix_at + 1)
    post_fix_result_at = kanon_tape.find(
        "Wait+Screen /KANON_LINT_CLEAN_OK/", post_fix_lint_at
    )
    gate_at = kanon_tape.find('kanon gate \\"$ALETHEIA\\"', post_fix_result_at)
    if not (
        seed_at
        < initial_lint_at
        < initial_result_at
        < fix_at
        < post_fix_lint_at
        < post_fix_result_at
        < gate_at
    ):
        fail(
            errors,
            "Kanon tape must re-run non-mutating lint cleanly after --fix and before gate",
        )
    for dangerous in ("git checkout --", "git reset", "$HOME/dev", "every public repo"):
        if dangerous in kanon_tape:
            fail(errors, f"Kanon tape retains dangerous or stale form: {dangerous!r}")

    harmonia_tape = Path("static/tapes/harmonia-serve.tape").read_text()
    for stale in ("/api/library/scan", "import queue", "populat"):
        if stale in harmonia_tape.lower():
            fail(errors, f"Harmonia tape retains no-op scan claim: {stale!r}")

    source_corpus = "\n".join(
        path.read_text()
        for path in [
            Path("config.toml"),
            Path("content/colophon.md"),
            Path("static/llms.txt"),
            Path("static/img/og-card.svg"),
        ]
    )
    for stale_claim in (
        "Recordings and receipts, not claims",
        "Every recording on one page",
    ):
        if stale_claim in source_corpus:
            fail(errors, f"stale recording claim remains: {stale_claim!r}")
    for stale_claim in (
        "third-party application dependencies",
        "No third-party application requests",
        "Every push runs",
        "Every response is authored `no-store, no-transform`",
    ):
        if stale_claim in source_corpus:
            fail(errors, f"stale dependency or trigger claim remains: {stale_claim!r}")

    authored_corpus = "\n".join(
        path.read_text()
        for path in list(Path("content").rglob("*.md"))
        + list(Path("static/tapes").glob("*.tape"))
        + [Path(".kanon-ci.toml")]
    )
    discredited = (
        "1.35 million training pairs",
        "97.5% cluster purity",
        "built directly from the Go source",
        "Single binary, no external services",
        "Gate-Passed: kanon 0.5.2 +ruleset:fleet-2026q2",
        "a mismatched or forged stamp rejects the push",
        "A grounding step now issues the evidence together with a token",
        "no unsafe beyond what the underlying `boringtun` crate",
        "Every rule is now tagged substance or proxy",
        "a gate stamp the server recomputes before honoring",
        "Bluetooth/GPS control, BT audio, mesh/inbox) sit unreachable",
    ) + FORBIDDEN_PUBLIC_VARIANTS
    for phrase in discredited:
        if phrase in authored_corpus:
            fail(errors, f"discredited or unlanded claim remains: {phrase!r}")

    judge_essay = Path("content/writing/hardest-honest-rung.md").read_text()
    if (
        "remain sequenced work" not in judge_essay
        or "generic labeled holdout" not in judge_essay
    ):
        fail(
            errors,
            "hardest-honest-rung must separate the landed holdout from sequenced judge work",
        )
    for required in ("remains roadmap work", "Error, Warning, and Info"):
        if required not in judge_essay:
            fail(
                errors,
                f"hardest-honest-rung lacks the current Kanon boundary: {required!r}",
            )
    counting_essay = Path("content/writing/three-ways-to-count.md").read_text()
    if "post-receive hook runs after the ref has moved" not in counting_essay:
        fail(
            errors, "three-ways-to-count must preserve the post-receive timing boundary"
        )

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
