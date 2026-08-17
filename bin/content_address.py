#!/usr/bin/env python3
"""Finalize a Zola tree with byte-bound physical public-resource identities.

Zola deliberately renders readable logical resource paths.  This finalizer is
the one release boundary that turns those paths into `/a/<sha256>.<ext>` URLs.
The digest names the *final served bytes*: dependencies in CSS are finalized
first, then their physical URLs are written into the parent before it is
hashed.  Stable HTML and protocol resources are rewritten only after the
complete map exists.

Not every non-HTML file Zola emits enters that map: `build_map` only
addresses `seed_candidates`' reachable set (candidates named by an actual
HTML/CSS/JSON/webmanifest/_headers/_redirects reference, transitively) plus
whatever canonical protocol members `release-resources.toml` declares. A
Zola output file no live reference ever names is dropped from this release
entirely -- never addressed, never left at its logical path. Already-retained
history is unaffected: `bin/asset_retention.py`'s ledger is append-only and
keyed on physical bytes already recorded, not on this build's reachable set.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import stat
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlparse

from asset_retention import (
    record_snapshot,
    snapshot_resources,
    validate_ledger,
)
from pages_limits import require_media_type_rule_capacity, require_static_file_size
from release_manifest import (
    BASE_URL,
    SPECIAL_MEDIA_TYPES,
    canonical_resource_path,
    css_reference_spans,
    html_url_attribute_names,
    json_ld_url_path,
    public_files,
    read_contract,
    resolve_browser_references,
    speculation_rules_url_path,
    valid_output_path,
    webmanifest_url_path,
)

MAP_SCHEMA_VERSION = 3
ADDRESS_PREFIX = "a"
ADDRESS_RE = re.compile(r"^a/([0-9a-f]{64})(\.[A-Za-z0-9]+)$")
WHATWG_EDGE_C0_OR_SPACE_RE = re.compile(r"^[\x00-\x20]+|[\x00-\x20]+$")
WHATWG_TAB_OR_NEWLINE_RE = re.compile(r"[\t\n\r]")
CACHE_BUSTER_RE = re.compile(r"(?:\?|&amp;|&)(?:h|v)=", re.IGNORECASE)
RETENTION_LEDGER = Path("asset-retention.json")
RETENTION_ASSETS = Path("retained-assets")
ATTRIBUTE_RE = re.compile(
    r"\s+(?P<name>[A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*"
    r"(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.DOTALL,
)
URL_TOKEN_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9+.-]*:[^\s<>'\"`]+|"
    r"(?<![A-Za-z0-9._~:/?&=#%+-])"
    r"/[A-Za-z0-9._~!$&()*+,;=:@%/?#\\-]+"
)
ABSOLUTE_HTTP_URL_RE = re.compile(
    r"https?:[^\s<>\[\]'\"`\\]+",
    re.IGNORECASE,
)
RAW_HTML_TAG_RE = re.compile(
    r"<\s*/?\s*[A-Za-z][A-Za-z0-9-]*(?=\s|/?>)",
    re.IGNORECASE,
)
MARKDOWN_INLINE_TARGET_RE = re.compile(
    r"!?\[[^\]\r\n]*\]\(\s*"
    r"(?:<(?P<angle>[^>\r\n]+)>|(?P<plain>[^\s()\r\n]+))"
    r"(?:\s+(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|\([^()\r\n]*\)))?\s*\)"
)
MARKDOWN_REFERENCE_TARGET_RE = re.compile(
    r"(?m)^[ \t]{0,3}\[[^\]\r\n]+\]:[ \t]*"
    r"(?:<(?P<angle>[^>\r\n]+)>|(?P<plain>\S+))"
)
MARKDOWN_AUTOLINK_RE = re.compile(
    r"<(?P<url>https?://[^\s<>]+)>",
    re.IGNORECASE,
)
ATOM_URL_ATTRIBUTES = {
    "category": frozenset({"scheme"}),
    "content": frozenset({"src"}),
    "generator": frozenset({"uri"}),
    "link": frozenset({"href"}),
}
ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"
ATOM_URL_TEXT_ELEMENTS = frozenset({"icon", "id", "logo", "uri"})
ATOM_TEXT_CONSTRUCTS = frozenset({"content", "rights", "subtitle", "summary", "title"})
SITEMAP_URL_ATTRIBUTES = {"link": frozenset({"href"})}
SITEMAP_URL_TEXT_ELEMENTS = frozenset({"loc"})
# WARNING: this string is an XML namespace identifier, not an endpoint. It is compared against
# element namespaces and never dereferenced, and the sitemap spec fixes the http:// form — changing
# it to https:// would stop matching every conforming sitemap.
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"  # kanon:ignore SECURITY/insecure-transport -- namespace identifier, never fetched
JAVASCRIPT_AUTHORITIES = {
    # Reviewed self-contained enhancement scripts. Updating any executable byte
    # is an explicit authority change, not something a heuristic URL scanner
    # may silently accept.
    "js/site.js": "84bc40ef96da7f949e0f1c87a6365c903fbd308058d0e91cc9cc24a42d5b27a1",
    "js/triad.js": "a38e394c7d5c963e7494cd88c9fa49f586c81a27661c9997f50456f3d4275492",
    # Vendored player accepts recording URLs supplied by already-validated HTML;
    # its reviewed minified distribution is otherwise immutable here.
    "vendor/asciinema/asciinema-player.min.js": (
        "a13c37632e1b5c49fe9128417b9319a9b5bc64cb457dd5ae52cbba8a3aceb880"
    ),
}
DEPENDENCY_CAPABLE_XML_SUFFIXES = frozenset(
    {".atom", ".kml", ".mathml", ".rdf", ".rss", ".xml", ".xhtml", ".xsl", ".xslt"}
)
ADDRESSABLE_SUFFIX_AUTHORITIES = frozenset(
    {
        ".avif",
        ".cast",
        ".css",
        ".gif",
        ".ico",
        ".jpeg",
        ".jpg",
        ".js",
        ".json",
        ".m4a",
        ".mjs",
        ".mp3",
        ".mp4",
        ".ogg",
        ".otf",
        ".pdf",
        ".png",
        ".sh",
        ".svg",
        ".tape",
        ".ttf",
        ".txt",
        ".vtt",
        ".wav",
        ".webm",
        ".webmanifest",
        ".webp",
        ".woff",
        ".woff2",
    }
)
ADDRESSABLE_JSON_AUTHORITIES = frozenset({"site.webmanifest", "speculation-rules.json"})


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def extension_for(logical_path: str) -> str:
    suffix = PurePosixPath(logical_path).suffix.lower()
    if not suffix or not re.fullmatch(r"\.[a-z0-9]+", suffix):
        raise ValueError(
            f"addressed resource needs one MIME-significant extension: {logical_path!r}"
        )
    return suffix


def physical_path(digest: str, logical_path: str) -> str:
    return f"{ADDRESS_PREFIX}/{digest}{extension_for(logical_path)}"


def serialize_map(
    resources: list[dict[str, str]], media_types: dict[str, str]
) -> bytes:
    value = {
        "schema_version": MAP_SCHEMA_VERSION,
        "resource_count": len(resources),
        "resources": sorted(resources, key=lambda item: item["logical_path"]),
        "media_types": dict(sorted(media_types.items())),
    }
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_atomic(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def whatwg_input_cleanup(value: str) -> str:
    """Reproduce the WHATWG basic URL parser's pre-parse string cleanup.

    Steps 1-2 of the living standard's basic URL parser strip leading and
    trailing C0-control-or-space, then remove every ASCII tab or newline
    from anywhere in the string, before parsing begins. A root-relative
    reference has no authority component, so those two steps are the only
    ones that can move its `pathname` relative to Python's `urlparse` -
    applying them here keeps the fast path WHATWG-equivalent without
    spawning the pinned Node parser for the site's most common reference
    shape.
    """
    edge_stripped = WHATWG_EDGE_C0_OR_SPACE_RE.sub("", value)
    return WHATWG_TAB_OR_NEWLINE_RE.sub("", edge_stripped)


_RESOLVED_CONSUMER_URL_CACHE: OrderedDict[tuple[str, str, bool], dict[str, str] | None] = (
    OrderedDict()
)
RESOLVED_CONSUMER_URL_CACHE_MAXSIZE = 4096


def _local_consumer_url(reference: str, base: str) -> dict[str, str]:
    parsed_reference = urlparse(reference)
    parsed_base = urlparse(base)
    return {
        "protocol": f"{parsed_base.scheme}:",
        "hostname": parsed_base.hostname or "",
        "port": str(parsed_base.port or ""),
        "pathname": parsed_reference.path,
        "search": f"?{parsed_reference.query}" if parsed_reference.query else "",
        "hash": (f"#{parsed_reference.fragment}" if parsed_reference.fragment else ""),
    }


def _cache_resolved_consumer_url(
    key: tuple[str, str, bool], resolved: dict[str, str] | None
) -> None:
    # PERF: bounded LRU, not an unbounded dict - a long-running build process
    # (the dev server, or a batch job over many pages) resolves references
    # from a working set that is large but not unbounded, so a plain dict
    # here is a slow memory leak nobody attributes to this cache. Evict the
    # least-recently-used entry once the bound is reached, same contract
    # the prior @lru_cache(maxsize=4096) decorator gave this function.
    _RESOLVED_CONSUMER_URL_CACHE[key] = resolved
    _RESOLVED_CONSUMER_URL_CACHE.move_to_end(key)
    if len(_RESOLVED_CONSUMER_URL_CACHE) > RESOLVED_CONSUMER_URL_CACHE_MAXSIZE:
        _RESOLVED_CONSUMER_URL_CACHE.popitem(last=False)


def resolved_consumer_url(
    reference: str, base: str, upgrade_insecure: bool
) -> dict[str, str] | None:
    key = (reference, base, upgrade_insecure)
    if key in _RESOLVED_CONSUMER_URL_CACHE:
        _RESOLVED_CONSUMER_URL_CACHE.move_to_end(key)
        return _RESOLVED_CONSUMER_URL_CACHE[key]
    if reference.startswith("/") and not reference.startswith("//"):
        cleaned_reference = whatwg_input_cleanup(reference)
        # WARNING: tab/newline removal runs on the whole string, so two literal
        # slashes separated only by stripped characters (e.g. "/\t/evil/x")
        # collapse into a network-path "//" prefix that was never in the raw
        # reference. That changes the resolved authority, not just the path -
        # fall through to the authoritative parser rather than assume this is
        # still a same-origin, path-only reference.
        if cleaned_reference.startswith("/") and not cleaned_reference.startswith("//"):
            resolved = _local_consumer_url(cleaned_reference, base)
        else:
            resolved = resolve_browser_references(
                [reference],
                [base],
                upgrade_insecure=upgrade_insecure,
            )[0]
    else:
        resolved = resolve_browser_references(
            [reference],
            [base],
            upgrade_insecure=upgrade_insecure,
        )[0]
    _cache_resolved_consumer_url(key, resolved)
    return resolved


def prime_resolved_consumer_url_cache(
    entries: list[tuple[str, str, bool]],
) -> None:
    """Resolve every not-yet-cached external reference in one batched call.

    PERF: resolved_consumer_url()'s fallback spawns one Node subprocess per
    call. A caller that loops over many references sharing one base/origin
    (a CSS file's url()s, an HTML document's attributes, a JSON document's
    URL fields) would otherwise pay one subprocess per unique reference.
    Callers that already hold the full reference list before resolving any
    of them (apply_reference_spans, rewrite_json, rewrite_url_tokens) prime
    the cache first so resolve_browser_references() is called once per
    upgrade_insecure group instead.
    """
    pending: dict[bool, list[tuple[str, str]]] = {}
    seen: set[tuple[str, str, bool]] = set()
    for reference, base, upgrade_insecure in entries:
        key = (reference, base, upgrade_insecure)
        if key in seen or key in _RESOLVED_CONSUMER_URL_CACHE:
            continue
        if reference.startswith("/") and not reference.startswith("//"):
            continue  # resolved_consumer_url() answers this locally, no subprocess
        seen.add(key)
        pending.setdefault(upgrade_insecure, []).append((reference, base))
    for upgrade_insecure, pairs in pending.items():
        resolved = resolve_browser_references(
            [reference for reference, _base in pairs],
            [base for _reference, base in pairs],
            upgrade_insecure=upgrade_insecure,
        )
        for (reference, base), result in zip(pairs, resolved, strict=True):
            _cache_resolved_consumer_url((reference, base, upgrade_insecure), result)


def same_origin_path(reference: str, base: str, origin: str) -> str | None:
    if "\\" in reference:
        raise ValueError(
            f"resource reference contains a forbidden backslash: {reference!r}"
        )
    if reference.startswith("//"):
        raise ValueError(
            f"network-path resource references are forbidden: {reference!r}"
        )
    parsed_origin = urlparse(origin)
    try:
        resolved = resolved_consumer_url(
            reference,
            base,
            parsed_origin.scheme == "https",
        )
    except ValueError as exc:
        raise ValueError(
            "resource reference cannot be resolved by the browser URL authority: "
            f"{reference!r}: {exc}"
        ) from exc
    if resolved is None:
        raise ValueError(f"resource reference is not a browser URL: {reference!r}")
    expected_port = str(parsed_origin.port or "")
    if (
        resolved["protocol"] != f"{parsed_origin.scheme}:"
        or resolved["hostname"] != parsed_origin.hostname
        or resolved["port"] != expected_port
    ):
        return None
    try:
        return canonical_resource_path(resolved["pathname"]).lstrip("/")
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(
            f"resource reference path is not canonicalizable: {reference!r}: {exc}"
        ) from exc


def replacement_for_reference(
    reference: str,
    *,
    base: str,
    origin: str,
    candidates: set[str],
    resolve,
) -> str | None:
    if not reference or reference.startswith("#"):
        return None
    dependency = same_origin_path(reference, base, origin)
    if dependency is None or dependency not in candidates:
        return None
    parsed_origin = urlparse(origin)
    resolved = resolved_consumer_url(
        reference,
        base,
        parsed_origin.scheme == "https",
    )
    if resolved is None:
        raise ValueError(f"resource reference is not a browser URL: {reference!r}")
    if resolved["search"] or resolved["hash"]:
        raise ValueError(
            f"addressed dependency must be query- and fragment-free: {reference!r}"
        )
    item = resolve(dependency)
    if urlparse(reference).scheme or reference.startswith("//"):
        return f"{origin}{item['request_url']}"
    return item["request_url"]


def apply_reference_spans(
    raw: str,
    spans: list[tuple[int, int, str]],
    *,
    base: str,
    origin: str,
    candidates: set[str],
    resolve,
) -> str:
    upgrade_insecure = urlparse(origin).scheme == "https"
    prime_resolved_consumer_url_cache(
        [(reference, base, upgrade_insecure) for _start, _end, reference in spans]
    )
    replacements: list[tuple[int, int, str]] = []
    for start, end, reference in spans:
        replacement = replacement_for_reference(
            reference,
            base=base,
            origin=origin,
            candidates=candidates,
            resolve=resolve,
        )
        if replacement is not None:
            replacements.append((start, end, replacement))
    cursor = len(raw)
    rewritten: list[str] = []
    for start, end, replacement in sorted(replacements, reverse=True):
        if not 0 <= start <= end <= cursor:
            raise ValueError("overlapping or invalid resource-reference spans")
        rewritten.append(raw[end:cursor])
        rewritten.append(replacement)
        cursor = start
    rewritten.append(raw[:cursor])
    return "".join(reversed(rewritten))


def json_value_string_spans(
    raw: str, label: str
) -> list[tuple[tuple[str | int, ...], int, int, str]]:
    """Return exact spans and structural paths for JSON string values."""
    from asset_retention import strict_json

    strict_json(raw, label)
    decoder = json.JSONDecoder()
    spans: list[tuple[tuple[str | int, ...], int, int, str]] = []
    index = 0

    def skip_space() -> None:
        nonlocal index
        while index < len(raw) and raw[index] in " \t\r\n":
            index += 1

    def parse_value(path: tuple[str | int, ...]) -> None:
        nonlocal index
        skip_space()
        character = raw[index]
        if character == '"':
            start = index
            value, index = decoder.raw_decode(raw, index)
            spans.append((path, start, index, value))
            return
        if character == "{":
            index += 1
            skip_space()
            if raw[index] == "}":
                index += 1
                return
            while True:
                skip_space()
                key, index = decoder.raw_decode(raw, index)
                skip_space()
                index += 1  # strict_json proved the required colon.
                parse_value((*path, key))
                skip_space()
                separator = raw[index]
                index += 1
                if separator == "}":
                    return
        if character == "[":
            index += 1
            skip_space()
            if raw[index] == "]":
                index += 1
                return
            item_index = 0
            while True:
                parse_value((*path, item_index))
                item_index += 1
                skip_space()
                separator = raw[index]
                index += 1
                if separator == "]":
                    return
        _value, index = decoder.raw_decode(raw, index)

    parse_value(())
    skip_space()
    if index != len(raw):  # pragma: no cover - strict_json owns this failure
        raise ValueError(f"{label}: trailing JSON content")
    return spans


def rewrite_json(
    raw: str,
    *,
    label: str,
    base: str,
    origin: str,
    candidates: set[str],
    resolve,
    selector,
) -> str:
    spans = [item for item in json_value_string_spans(raw, label) if selector(item[0])]
    upgrade_insecure = urlparse(origin).scheme == "https"
    prime_resolved_consumer_url_cache(
        [
            (value, base, upgrade_insecure)
            for _path, _start, _end, value in spans
            if value
            and not value.startswith("#")
            and (value.startswith(("/", "?")) or urlparse(value).scheme)
        ]
    )
    replacements: list[tuple[int, int, str]] = []
    for path, start, end, value in spans:
        if (
            value
            and not value.startswith(("/", "#", "?"))
            and not urlparse(value).scheme
        ):
            raise ValueError(
                f"{label}: path-relative JSON URL field is forbidden: {value!r}"
            )
        replacement = replacement_for_reference(
            value,
            base=base,
            origin=origin,
            candidates=candidates,
            resolve=resolve,
        )
        if replacement is not None:
            replacements.append((start, end, json.dumps(replacement)))
    cursor = len(raw)
    rewritten: list[str] = []
    for start, end, replacement in sorted(replacements, reverse=True):
        if end > cursor:
            raise ValueError(f"{label}: overlapping JSON string spans")
        rewritten.append(raw[end:cursor])
        rewritten.append(replacement)
        cursor = start
    rewritten.append(raw[:cursor])
    return "".join(reversed(rewritten))


class HtmlReferenceSpanParser(HTMLParser):
    def __init__(self, raw: str, label: str, *, embedded_atom: bool = False) -> None:
        super().__init__(convert_charrefs=False)
        self.raw = raw
        self.label = label
        self.embedded_atom = embedded_atom
        self.line_offsets: list[int] = [0]
        self.spans: list[tuple[int, int, str]] = []
        self.json_blocks: list[tuple[int, int]] = []
        self.json_start: int | None = None
        for match in re.finditer(r"\n", raw):
            self.line_offsets.append(match.end())

    def absolute_offset(self) -> int:
        line, column = self.getpos()
        return self.line_offsets[line - 1] + column

    def collect_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        start = self.absolute_offset()
        source = self.get_starttag_text() or ""
        normalized_tag = tag.lower()
        if self.embedded_atom:
            forbidden_elements = {
                "base",
                "embed",
                "fencedframe",
                "form",
                "frame",
                "iframe",
                "link",
                "math",
                "meta",
                "object",
                "portal",
                "script",
                "style",
                "svg",
            }
            if normalized_tag in forbidden_elements:
                raise ValueError(
                    f"{self.label}: embedded Atom HTML forbids active or "
                    f"style-bearing element <{normalized_tag}>"
                )
            forbidden_attributes = sorted(
                name.lower()
                for name, value in attrs
                if value is not None
                and (name.lower() == "style" or name.lower().startswith("on"))
            )
            if forbidden_attributes:
                raise ValueError(
                    f"{self.label}: embedded Atom HTML forbids inline style or "
                    f"event attributes: {forbidden_attributes}"
                )
        unsupported_compound = sorted(
            name.lower()
            for name, value in attrs
            if value
            and name.lower()
            in {"archive", "attributionsrc", "imagesrcset", "ping", "srcdoc", "srcset"}
        )
        if unsupported_compound:
            raise ValueError(
                f"{self.label}: compound HTML URL attributes are forbidden until "
                f"their grammar is validated: {unsupported_compound}"
            )
        lexical = list(ATTRIBUTE_RE.finditer(source))
        url_names = html_url_attribute_names(tag, attrs)
        quoted_url_names = {
            match.group("name").lower()
            for match in lexical
            if match.group("name").lower() in url_names
        }
        parsed_url_names = {
            name.lower()
            for name, value in attrs
            if name.lower() in url_names and value is not None
        }
        if not parsed_url_names.issubset(quoted_url_names):
            raise ValueError(f"{self.label}: HTML resource URL attributes must be quoted")
        for match in lexical:
            if match.group("name").lower() not in url_names:
                continue
            self.spans.append(
                (
                    start + match.start("value"),
                    start + match.end("value"),
                    html.unescape(match.group("value")),
                )
            )
        media_type = ""
        for name, value in attrs:
            if name.lower() == "type":
                media_type = (value or "").split(";", 1)[0].strip().lower()
        if tag.lower() == "script" and media_type == "application/ld+json":
            if self.json_start is not None:
                raise ValueError(
                    f"{self.label}: nested application/ld+json blocks are forbidden"
                )
            self.json_start = start + len(source)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.collect_tag(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.collect_tag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.json_start is not None:
            self.json_blocks.append((self.json_start, self.absolute_offset()))
            self.json_start = None


def rewrite_html(
    raw: str,
    *,
    label: str,
    base: str,
    origin: str,
    candidates: set[str],
    resolve,
) -> str:
    parser = HtmlReferenceSpanParser(raw, label)
    parser.feed(raw)
    parser.close()
    if parser.json_start is not None:
        raise ValueError(f"{label}: unterminated application/ld+json block")
    spans = list(parser.spans)
    for start, end in parser.json_blocks:
        block = raw[start:end]
        for path, token_start, token_end, value in json_value_string_spans(
            block, f"{label} application/ld+json"
        ):
            if not json_ld_url_path(path):
                continue
            # Physical request URLs contain no characters requiring JSON or
            # HTML escaping, so replacing only the quoted token's content is
            # byte-stable for unrelated JSON-LD fields.
            spans.append((start + token_start + 1, start + token_end - 1, value))
    return apply_reference_spans(
        raw,
        spans,
        base=base,
        origin=origin,
        candidates=candidates,
        resolve=resolve,
    )


def rewrite_url_tokens(
    raw: str,
    *,
    base: str,
    origin: str,
    candidates: set[str],
    resolve,
) -> str:
    replacements: list[tuple[int, int, str]] = []

    def embeds_logical_path(token: str) -> bool:
        for candidate in candidates:
            match = re.search(rf"/{re.escape(candidate)}(?=$|[^A-Za-z0-9._/-])", token)
            if match is not None:
                return True
        return False

    upgrade_insecure = urlparse(origin).scheme == "https"
    prime_resolved_consumer_url_cache(
        [
            (match.group(0), base, upgrade_insecure)
            for match in URL_TOKEN_RE.finditer(raw)
            if match.group(0) and not match.group(0).startswith("#")
        ]
    )
    for match in URL_TOKEN_RE.finditer(raw):
        reference = match.group(0)
        replacement = replacement_for_reference(
            reference,
            base=base,
            origin=origin,
            candidates=candidates,
            resolve=resolve,
        )
        if replacement is not None:
            replacements.append((match.start(), match.end(), replacement))
            continue
        dependency = same_origin_path(reference, base, origin)
        parsed = urlparse(reference)
        if embeds_logical_path(reference) and not (
            parsed.scheme in {"http", "https"} and dependency is None
        ):
            raise ValueError(
                "addressed logical path is embedded in an unsupported or ambiguous "
                f"URI token: {reference!r}"
            )

    cursor = len(raw)
    rewritten: list[str] = []
    for start, end, replacement in sorted(replacements, reverse=True):
        if not 0 <= start <= end <= cursor:
            raise ValueError("overlapping or invalid URI-token spans")
        rewritten.append(raw[end:cursor])
        rewritten.append(replacement)
        cursor = start
    rewritten.append(raw[:cursor])
    return "".join(reversed(rewritten))


def rewrite_selected_references(
    raw: str,
    spans: list[tuple[int, int, str]],
    *,
    base: str,
    origin: str,
    candidates: set[str],
    resolve,
) -> str:
    replacements: list[tuple[int, int, str]] = []
    for start, end, reference in spans:
        rewritten = rewrite_url_tokens(
            reference,
            base=base,
            origin=origin,
            candidates=candidates,
            resolve=resolve,
        )
        if rewritten != reference:
            replacements.append((start, end, rewritten))
    cursor = len(raw)
    chunks: list[str] = []
    for start, end, replacement in sorted(replacements, reverse=True):
        if not 0 <= start <= end <= cursor:
            raise ValueError("overlapping or invalid selected-reference spans")
        chunks.extend((raw[end:cursor], replacement))
        cursor = start
    chunks.append(raw[:cursor])
    return "".join(reversed(chunks))


def rewrite_headers_consumer(
    raw: str,
    *,
    base: str,
    origin: str,
    candidates: set[str],
    resolve,
) -> str:
    spans: list[tuple[int, int, str]] = []
    offset = 0
    for line in raw.splitlines(keepends=True):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and line[0].isspace():
            name, separator, value = stripped.partition(":")
            if separator and name.lower() == "speculation-rules":
                match = re.fullmatch(r"(['\"])(/[^'\"]+)\1", value.strip())
                if match is None:
                    raise ValueError(
                        "Speculation-Rules must contain one quoted same-origin URL"
                    )
                local_start = line.index(match.group(2))
                spans.append(
                    (
                        offset + local_start,
                        offset + local_start + len(match.group(2)),
                        match.group(2),
                    )
                )
        elif stripped.startswith("/"):
            local_start = line.index(stripped)
            spans.append(
                (offset + local_start, offset + local_start + len(stripped), stripped)
            )
        offset += len(line)
    return rewrite_selected_references(
        raw,
        spans,
        base=base,
        origin=origin,
        candidates=candidates,
        resolve=resolve,
    )


def rewrite_redirects_consumer(
    raw: str,
    *,
    base: str,
    origin: str,
    candidates: set[str],
    resolve,
) -> str:
    spans: list[tuple[int, int, str]] = []
    offset = 0
    for line in raw.splitlines(keepends=True):
        body = line.split("#", 1)[0]
        tokens = list(re.finditer(r"\S+", body))
        if tokens:
            if len(tokens) != 3:
                raise ValueError(
                    "_redirects line must contain source, target, and status"
                )
            target = tokens[1]
            spans.append(
                (
                    offset + target.start(),
                    offset + target.end(),
                    target.group(0),
                )
            )
        offset += len(line)
    return rewrite_selected_references(
        raw,
        spans,
        base=base,
        origin=origin,
        candidates=candidates,
        resolve=resolve,
    )


def markdown_code_ranges(raw: str) -> list[tuple[int, int]]:
    """Return fenced and inline code ranges excluded from Markdown URL grammar."""
    ranges: list[tuple[int, int]] = []
    fence: tuple[str, int, int] | None = None
    offset = 0
    for line in raw.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        marker = re.match(r" {0,3}(?P<run>`{3,}|~{3,})(?P<info>.*)", body)
        if fence is None and marker is not None:
            run = marker.group("run")
            if run[0] == "`" and "`" in marker.group("info"):
                raise ValueError(
                    "backtick fence info strings containing backticks are forbidden"
                )
            fence = (run[0], len(run), offset)
        elif fence is not None:
            character, length, start = fence
            if re.fullmatch(
                rf" {{0,3}}{re.escape(character)}{{{length},}}[ \t]*", body
            ):
                ranges.append((start, offset + len(line)))
                fence = None
        offset += len(line)
    if fence is not None:
        ranges.append((fence[2], len(raw)))

    def covered(index: int) -> tuple[int, int] | None:
        return next((item for item in ranges if item[0] <= index < item[1]), None)

    index = 0
    while index < len(raw):
        existing = covered(index)
        if existing is not None:
            index = existing[1]
            continue
        if raw[index] != "`":
            index += 1
            continue
        if is_backslash_escaped(raw, index):
            index += 1
            continue
        start = index
        while index < len(raw) and raw[index] == "`":
            index += 1
        length = index - start
        search = index
        while True:
            closing = raw.find("`" * length, search)
            if closing < 0:
                break
            before_is_tick = closing > 0 and raw[closing - 1] == "`"
            after = closing + length
            after_is_tick = after < len(raw) and raw[after] == "`"
            if not before_is_tick and not after_is_tick and covered(closing) is None:
                ranges.append((start, after))
                index = after
                break
            search = closing + 1
    return sorted(ranges)


def span_overlaps(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(
        start < range_end and end > range_start for range_start, range_end in ranges
    )


def is_backslash_escaped(raw: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and raw[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def rewrite_text_consumer(
    raw: str,
    *,
    label: str,
    base: str,
    origin: str,
    candidates: set[str],
    resolve,
) -> str:
    spans: list[tuple[int, int, str]] = []
    if label == "robots.txt":
        offset = 0
        for line in raw.splitlines(keepends=True):
            match = re.match(r"\s*Sitemap:\s*(\S+)", line, re.IGNORECASE)
            if match is not None:
                spans.append(
                    (
                        offset + match.start(1),
                        offset + match.end(1),
                        match.group(1),
                    )
                )
            offset += len(line)
    else:
        if re.search(
            r"(?m)^(?: {4,}|\t).*(?:https?://|\]\(|\]:\s*)",
            raw,
            re.IGNORECASE,
        ):
            raise ValueError(
                f"{label}: indented Markdown code containing URL syntax is forbidden"
            )
        code_ranges = markdown_code_ranges(raw)
        for match in RAW_HTML_TAG_RE.finditer(raw):
            if not span_overlaps(match.start(), match.end(), code_ranges) and not (
                is_backslash_escaped(raw, match.start())
            ):
                raise ValueError(
                    f"{label}: raw HTML is forbidden in agent-facing Markdown"
                )
        syntax_ranges: list[tuple[int, int]] = []
        for match in MARKDOWN_INLINE_TARGET_RE.finditer(raw):
            group = "angle" if match.group("angle") is not None else "plain"
            closing_bracket = raw.rfind("]", match.start(), match.start(group))
            if (
                span_overlaps(match.start(), match.end(), code_ranges)
                or (is_backslash_escaped(raw, match.start()))
                or closing_bracket < 0
                or is_backslash_escaped(raw, closing_bracket)
            ):
                continue
            spans.append((match.start(group), match.end(group), match.group(group)))
            syntax_ranges.append((match.start(), match.end()))
        for match in MARKDOWN_REFERENCE_TARGET_RE.finditer(raw):
            if span_overlaps(match.start(), match.end(), code_ranges):
                continue
            group = "angle" if match.group("angle") is not None else "plain"
            spans.append((match.start(group), match.end(group), match.group(group)))
            line_end = raw.find("\n", match.end())
            syntax_ranges.append(
                (match.start(), len(raw) if line_end < 0 else line_end + 1)
            )
        for match in MARKDOWN_AUTOLINK_RE.finditer(raw):
            if span_overlaps(match.start(), match.end(), code_ranges) or (
                is_backslash_escaped(raw, match.start())
            ):
                continue
            spans.append((match.start("url"), match.end("url"), match.group("url")))
            syntax_ranges.append((match.start(), match.end()))
        for match in ABSOLUTE_HTTP_URL_RE.finditer(raw):
            if span_overlaps(
                match.start(), match.end(), [*code_ranges, *syntax_ranges]
            ):
                continue
            if (
                match.start() > 0
                and raw[match.start() - 1] == "<"
                and (is_backslash_escaped(raw, match.start() - 1))
            ):
                continue
            end = match.end()
            while end > match.start() and raw[end - 1] in ".,;:!?)]}*":
                end -= 1
            spans.append((match.start(), end, raw[match.start() : end]))
        for _start, _end, reference in spans:
            if html.unescape(reference) != reference:
                raise ValueError(
                    f"{label}: Markdown destination character references are forbidden"
                )
            if "\\" in reference:
                raise ValueError(f"{label}: Markdown destination escapes are forbidden")
            if (
                reference
                and not reference.startswith(("/", "#", "?"))
                and not urlparse(reference).scheme
            ):
                raise ValueError(
                    f"{label}: path-relative Markdown destinations are forbidden: "
                    f"{reference!r}"
                )
    return rewrite_selected_references(
        raw,
        spans,
        base=base,
        origin=origin,
        candidates=candidates,
        resolve=resolve,
    )


def validate_xml_consumer(
    raw: str,
    *,
    label: str,
    base: str,
    origin: str,
    candidates: set[str],
    resolve,
) -> str:
    if re.search(r"<!DOCTYPE\b", raw, re.IGNORECASE):
        raise ValueError(f"{label}: XML document types are forbidden")
    without_declaration = re.sub(
        r"^\ufeff?<\?xml\s[^?]*\?>",
        "",
        raw,
        count=1,
        flags=re.IGNORECASE,
    )
    if "<?" in without_declaration:
        raise ValueError(f"{label}: XML processing instructions are forbidden")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"{label}: XML is not well formed: {exc}") from exc
    if root.tag.startswith("{"):
        root_namespace, _, root_local = root.tag[1:].partition("}")
    else:
        root_namespace, root_local = "", root.tag
    root_name = root_local.lower()
    if (
        label == "atom.xml"
        and root_name == "feed"
        and root_namespace
        in {
            "",
            ATOM_NAMESPACE,
        }
    ):
        url_attributes = ATOM_URL_ATTRIBUTES
        url_text_elements = ATOM_URL_TEXT_ELEMENTS
    elif (
        label == "sitemap.xml"
        and root_name == "urlset"
        and root_namespace
        in {
            "",
            SITEMAP_NAMESPACE,
        }
    ):
        url_attributes = SITEMAP_URL_ATTRIBUTES
        url_text_elements = SITEMAP_URL_TEXT_ELEMENTS
    else:
        raise ValueError(
            f"{label}: canonical XML root and namespace do not match its owned schema"
        )
    references: list[str] = []
    for element in root.iter():
        if element.tag.startswith("{"):
            element_namespace, _, element_local = element.tag[1:].partition("}")
        else:
            element_namespace, element_local = "", element.tag
        if element_namespace != root_namespace:
            raise ValueError(f"{label}: foreign XML extension namespaces are forbidden")
        local_element = element_local.lower()
        if local_element in url_text_elements and element.text:
            references.append(element.text.strip())
        for name in element.attrib:
            if name == "{http://www.w3.org/XML/1998/namespace}base":
                raise ValueError(f"{label}: xml:base is forbidden")
            if name.startswith("{") and name not in {
                "{http://www.w3.org/XML/1998/namespace}lang"
            }:
                raise ValueError(
                    f"{label}: foreign XML attribute namespaces are forbidden"
                )
        element_type = element.attrib.get("type", "").strip().lower()
        if local_element in ATOM_TEXT_CONSTRUCTS and (
            element_type == "xhtml" or len(element) > 0
        ):
            raise ValueError(f"{label}: inline Atom XML content is forbidden")
        if (
            local_element in ATOM_TEXT_CONSTRUCTS
            and element_type == "html"
            and element.text
        ):
            embedded = HtmlReferenceSpanParser(
                element.text, f"{label} embedded Atom HTML", embedded_atom=True
            )
            embedded.feed(element.text)
            embedded.close()
            references.extend(reference for _start, _end, reference in embedded.spans)
            for block_start, block_end in embedded.json_blocks:
                block = element.text[block_start:block_end]
                references.extend(
                    value
                    for path, _start, _end, value in json_value_string_spans(
                        block, f"{label} embedded Atom JSON-LD"
                    )
                    if json_ld_url_path(path)
                )
        for name, value in element.attrib.items():
            local_name = name.rsplit("}", 1)[-1].lower()
            if local_name in url_attributes.get(local_element, ()):
                references.append(value)
    for reference in references:
        inspected_reference = reference
        if (
            reference
            and not reference.startswith(("/", "#", "?"))
            and not urlparse(reference).scheme
        ):
            inspected_reference = urljoin(base, reference)
        rewritten = rewrite_url_tokens(
            inspected_reference,
            base=base,
            origin=origin,
            candidates=candidates,
            resolve=resolve,
        )
        if rewritten != inspected_reference:
            raise ValueError(
                f"{label}: canonical XML must not depend on an addressed resource: "
                f"{reference!r}"
            )
    return raw


def validate_javascript_authority(logical_path: str, body: bytes) -> None:
    expected = JAVASCRIPT_AUTHORITIES.get(logical_path)
    digest = sha256_bytes(body)
    if expected is None:
        raise ValueError(
            f"{logical_path}: JavaScript is outside the closed executable authority"
        )
    if digest != expected:
        raise ValueError(
            f"{logical_path}: JavaScript bytes differ from the reviewed authority; "
            f"expected {expected}, SHA-256={digest}"
        )


def validate_source_tree(output: Path, manifest_name: str) -> None:
    if (output / ADDRESS_PREFIX).exists():
        raise ValueError(
            f"reserved physical-address directory already exists: {ADDRESS_PREFIX}/"
        )
    for path in sorted(output.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(
                f"public artifact must not be a symlink: {path.relative_to(output)}"
            )
        if not stat.S_ISREG(metadata.st_mode):
            continue
        relative = path.relative_to(output).as_posix()
        if relative == manifest_name:
            raise ValueError(
                f"stale release manifest exists before finalization: {relative}"
            )


def select_consumers(output: Path, excluded: set[str]) -> list[Path]:
    """Text files eligible to carry a same-origin resource reference.

    Every regular file that is not itself a candidate resource, restricted
    to the formats `rewrite_consumer` knows how to scan. The reachability
    discovery pass and the real finalize pass both call this, so they always
    agree on what counts as a reference root -- one selection, not two that
    could drift.
    """
    consumers: list[Path] = []
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(output).as_posix()
        if relative in excluded:
            continue
        if path.name in {"_headers", "_redirects"} or path.suffix.lower() in {
            ".html",
            ".json",
            ".xml",
            ".txt",
            ".webmanifest",
        }:
            consumers.append(path)
    return consumers


def rewrite_consumer(
    path: Path,
    *,
    output: Path,
    origin: str,
    candidates: set[str],
    resolve,
) -> str:
    """Scan and rewrite one consumer file's same-origin resource references.

    The single authority both `finalize_tree` (rewrite: candidates is the
    finalized physical mapping) and `seed_candidates` (record: candidates is
    every emitted-but-not-yet-decided resource) read reference grammar from
    -- there is no second implementation of "what counts as a reference" to
    drift out of step with this one.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"text consumer is not strict UTF-8: {path.relative_to(output)}: {exc}"
        ) from exc
    relative = path.relative_to(output).as_posix()
    if relative == "index.html":
        base = f"{origin}/"
    elif relative.endswith("/index.html"):
        base = f"{origin}/{relative.removesuffix('index.html')}"
    else:
        base = f"{origin}/{relative}"
    suffix = path.suffix.lower()
    if suffix == ".html":
        return rewrite_html(
            text,
            label=relative,
            base=base,
            origin=origin,
            candidates=candidates,
            resolve=resolve,
        )
    if suffix in {".json", ".webmanifest"}:
        return rewrite_json(
            text,
            label=relative,
            base=base,
            origin=origin,
            candidates=candidates,
            resolve=resolve,
            selector=lambda _path: False,
        )
    if relative == "_headers":
        return rewrite_headers_consumer(
            text, base=base, origin=origin, candidates=candidates, resolve=resolve
        )
    if relative == "_redirects":
        return rewrite_redirects_consumer(
            text, base=base, origin=origin, candidates=candidates, resolve=resolve
        )
    if suffix == ".xml":
        return validate_xml_consumer(
            text,
            label=relative,
            base=base,
            origin=origin,
            candidates=candidates,
            resolve=resolve,
        )
    if suffix == ".txt":
        return rewrite_text_consumer(
            text,
            label=relative,
            base=base,
            origin=origin,
            candidates=candidates,
            resolve=resolve,
        )
    raise ValueError(f"unsupported public text consumer: {relative}")


def seed_candidates(output: Path, candidate_keys: set[str], origin: str) -> set[str]:
    """Resources named by a same-origin reference in consumer text.

    This is the root set `build_map` addresses. Its own CSS/JSON dependency
    resolution (`finalize`, in `build_map`) extends the root set
    transitively -- a font a reachable stylesheet references becomes
    reachable too -- so a Zola output file no consumer text and no reachable
    stylesheet/JSON ever names is never finalized: it enters neither the
    physical namespace nor a new asset-map entry, and never enters a future
    asset-retention snapshot. Already-retained history is untouched (that
    ledger is append-only and keyed on physical bytes, not on this reachable
    set -- see `bin/asset_retention.py`'s module docstring).

    Fails closed by construction, not by a separate guess: this calls the
    exact reference grammar `finalize_tree` later applies to rewrite these
    same files, with `candidates` widened to every currently emitted
    resource (not yet narrowed to what's reachable) so a reference this pass
    cannot resolve is a reference the real rewrite could not have resolved
    either -- `rewrite_consumer` raises rather than silently drop it, and an
    unresolved-but-present reference is a hard failure rather than a
    resource silently marked unreachable.
    """
    seeds: set[str] = set()

    def record(dependency: str) -> dict[str, str]:
        seeds.add(dependency)
        return {"request_url": f"/{dependency}"}

    for path in select_consumers(output, candidate_keys):
        rewrite_consumer(
            path,
            output=output,
            origin=origin,
            candidates=candidate_keys,
            resolve=record,
        )
    return seeds


def build_map(
    output: Path,
    *,
    canonical: set[str],
    manifest_name: str,
    origin: str,
) -> tuple[dict[str, dict[str, str]], dict[str, bytes], set[str]]:
    candidates = {
        path.relative_to(output).as_posix(): path
        for path in public_files(output, manifest_name)
        if path.relative_to(output).as_posix() not in canonical
    }
    if not candidates:
        raise ValueError("release has no addressable resources")
    for logical_path in candidates:
        if not valid_output_path(logical_path) or logical_path.startswith(
            f"{ADDRESS_PREFIX}/"
        ):
            raise ValueError(f"invalid logical resource path: {logical_path!r}")
    javascript_paths = {
        logical_path
        for logical_path in candidates
        if PurePosixPath(logical_path).suffix.lower() in {".js", ".mjs"}
    }
    if not javascript_paths.issubset(JAVASCRIPT_AUTHORITIES):
        raise ValueError(
            "addressed JavaScript includes a path outside the closed executable authority; "
            f"allowed={sorted(JAVASCRIPT_AUTHORITIES)}, "
            f"found={sorted(javascript_paths)}"
        )
    unsupported_xml = sorted(
        logical_path
        for logical_path in candidates
        if PurePosixPath(logical_path).suffix.lower() in DEPENDENCY_CAPABLE_XML_SUFFIXES
    )
    if unsupported_xml:
        raise ValueError(
            "dependency-capable XML cannot enter the addressed namespace; "
            f"declare a validated canonical protocol resource instead: {unsupported_xml}"
        )
    unknown_suffixes = sorted(
        logical_path
        for logical_path in candidates
        if PurePosixPath(logical_path).suffix.lower()
        not in ADDRESSABLE_SUFFIX_AUTHORITIES
    )
    if unknown_suffixes:
        raise ValueError(
            "addressed resource extension is outside the closed format authority; "
            f"found={unknown_suffixes}"
        )
    unknown_json = sorted(
        logical_path
        for logical_path in candidates
        if PurePosixPath(logical_path).suffix.lower() in {".json", ".webmanifest"}
        and logical_path not in ADDRESSABLE_JSON_AUTHORITIES
    )
    if unknown_json:
        raise ValueError(
            "addressed JSON is outside the closed schema authority; "
            f"allowed={sorted(ADDRESSABLE_JSON_AUTHORITIES)}, found={unknown_json}"
        )

    mapping: dict[str, dict[str, str]] = {}
    finalized_bodies: dict[str, bytes] = {}
    state: dict[str, str] = {}
    physical_owners: dict[str, str] = {}

    def finalize(logical_path: str, chain: tuple[str, ...] = ()) -> dict[str, str]:
        if logical_path in mapping:
            return mapping[logical_path]
        if state.get(logical_path) == "visiting":
            cycle = " -> ".join((*chain, logical_path))
            raise ValueError(f"addressed-resource dependency cycle: {cycle}")
        state[logical_path] = "visiting"
        body = candidates[logical_path].read_bytes()

        suffix = PurePosixPath(logical_path).suffix.lower()
        if suffix == ".css":
            try:
                text = body.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"CSS is not strict UTF-8: {logical_path}: {exc}"
                ) from exc
            errors: list[str] = []
            references = css_reference_spans(text, logical_path, errors)
            if errors:
                raise ValueError("; ".join(errors))
            base = f"{origin}/{logical_path}"
            for _start, _end, reference in references:
                if reference.startswith("#"):
                    continue
                dependency = same_origin_path(reference, base, origin)
                if dependency is not None and dependency not in candidates:
                    raise ValueError(
                        "addressed CSS dependency is not a retained addressable "
                        f"resource: {logical_path}: {reference!r}"
                    )
            text = apply_reference_spans(
                text,
                references,
                base=base,
                origin=origin,
                candidates=set(candidates),
                resolve=lambda dependency: finalize(dependency, (*chain, logical_path)),
            )
            body = text.encode("utf-8")
        elif suffix in {".json", ".webmanifest"}:
            try:
                text = body.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"addressed JSON is not strict UTF-8: {logical_path}: {exc}"
                ) from exc
            text = rewrite_json(
                text,
                label=logical_path,
                base=f"{origin}/{logical_path}",
                origin=origin,
                candidates=set(candidates),
                resolve=lambda dependency: finalize(dependency, (*chain, logical_path)),
                selector=(
                    webmanifest_url_path
                    if logical_path == "site.webmanifest"
                    else speculation_rules_url_path
                ),
            )
            body = text.encode("utf-8")
        elif suffix in {".js", ".mjs"}:
            validate_javascript_authority(logical_path, body)

        digest = sha256_bytes(body)
        output_path = physical_path(digest, logical_path)
        owner = physical_owners.get(output_path)
        if owner is not None and owner != logical_path:
            raise ValueError(
                "two logical resources collapse to one physical identity: "
                f"{owner!r}, {logical_path!r} -> {output_path!r}"
            )
        physical_owners[output_path] = logical_path
        item = {
            "logical_path": logical_path,
            "output_path": output_path,
            "request_url": f"/{output_path}",
            "sha256": digest,
            "cache_class": "addressed",
        }
        mapping[logical_path] = item
        finalized_bodies[output_path] = body
        state[logical_path] = "done"
        return item

    for logical_path in sorted(seed_candidates(output, set(candidates), origin)):
        finalize(logical_path)
    return mapping, finalized_bodies, set(candidates) - set(mapping)


def finalize_tree(
    output: Path,
    map_path: Path,
    origin: str,
    contract: dict,
    *,
    retention_ledger: Path | None = None,
    retention_assets: Path | None = None,
    record_retention_snapshot: bool = False,
) -> dict:
    output = output.resolve()
    map_path = map_path.resolve()
    parsed_origin = urlparse(origin)
    if (
        parsed_origin.scheme not in {"http", "https"}
        or not parsed_origin.hostname
        or parsed_origin.path not in {"", "/"}
        or parsed_origin.query
        or parsed_origin.fragment
        or origin.endswith("/")
    ):
        raise ValueError("base URL must be one HTTP(S) origin without a trailing slash")
    if map_path == output or output in map_path.parents:
        raise ValueError("asset map must live outside the deployed output")

    manifest_name = contract["manifest_name"]
    canonical = set(contract["canonical_paths"])
    validate_source_tree(output, manifest_name)
    mapping, finalized_bodies, excluded = build_map(
        output,
        canonical=canonical,
        manifest_name=manifest_name,
        origin=origin,
    )
    current_resources = sorted(mapping.values(), key=lambda item: item["logical_path"])
    resources = list(current_resources)
    media_types = {
        item["request_url"]: SPECIAL_MEDIA_TYPES[item["logical_path"]]
        for item in current_resources
        if item["logical_path"] in SPECIAL_MEDIA_TYPES
    }
    if (retention_ledger is None) != (retention_assets is None):
        raise ValueError(
            "asset retention ledger and asset root must be supplied together"
        )
    if retention_ledger is not None and retention_assets is not None:
        retention_ledger = retention_ledger.resolve()
        retention_assets = retention_assets.resolve()
        for authority_path in (retention_ledger, retention_assets):
            if authority_path == output or output in authority_path.parents:
                raise ValueError("asset retention authority must live outside output")
        if record_retention_snapshot:
            record_snapshot(
                retention_ledger,
                retention_assets,
                current_resources,
                finalized_bodies,
            )
        ledger, retained_bodies = validate_ledger(retention_ledger, retention_assets)
        expected_snapshot = snapshot_resources(current_resources)
        if ledger["entries"][-1]["resources"] != expected_snapshot:
            raise ValueError(
                "latest asset-retention snapshot differs from this finalized release; "
                "run `python3 bin/site.py retain-assets` and commit the updated ledger "
                "before deployment"
            )
        for output_path, body in retained_bodies.items():
            current = finalized_bodies.get(output_path)
            if current is not None and current != body:
                raise ValueError(f"retained physical identity collision: {output_path}")
            finalized_bodies[output_path] = body
        current_outputs = {item["output_path"] for item in current_resources}
        resources.extend(
            {
                "logical_path": output_path,
                "output_path": output_path,
                "request_url": f"/{output_path}",
                "sha256": sha256_bytes(body),
                "cache_class": "retained",
            }
            for output_path, body in sorted(retained_bodies.items())
            if output_path not in current_outputs
        )
        for entry in ledger["entries"]:
            for item in entry["resources"]:
                # WHY: a checkpoint entry's logical_path is synthesized
                # (`checkpoint/<hash>/<basename>`, record_checkpoint()), not
                # the resource's real name, so membership is recovered from
                # the basename rather than an exact-key match.
                media_type = SPECIAL_MEDIA_TYPES.get(
                    PurePosixPath(item["logical_path"]).name
                )
                if media_type is None:
                    continue
                request_url = f"/{item['output_path']}"
                prior = media_types.get(request_url)
                if prior is not None and prior != media_type:
                    raise ValueError(
                        f"conflicting retained media type for {request_url}"
                    )
                media_types[request_url] = media_type

    require_media_type_rule_capacity(len(media_types))
    for output_path, body in finalized_bodies.items():
        require_static_file_size(len(body), f"physical resource {output_path}")

    consumers = select_consumers(output, set(mapping))
    rewritten: dict[Path, bytes] = {}
    for path in consumers:
        relative = path.relative_to(output).as_posix()
        text = rewrite_consumer(
            path,
            output=output,
            origin=origin,
            candidates=set(mapping),
            resolve=mapping.__getitem__,
        )
        if relative == "_headers":
            current_special_urls = {
                item["request_url"]
                for item in current_resources
                if item["logical_path"] in SPECIAL_MEDIA_TYPES
            }
            historical_rules = [
                (request_url, media_type)
                for request_url, media_type in sorted(media_types.items())
                if request_url not in current_special_urls
            ]
            if historical_rules:
                text = text.rstrip() + "\n"
                for request_url, media_type in historical_rules:
                    text += f"\n{request_url}\n  Content-Type: {media_type}\n"
        if CACHE_BUSTER_RE.search(text):
            raise ValueError(
                f"legacy query cache-buster survives finalization: {path.relative_to(output)}"
            )
        rewritten[path] = text.encode("utf-8")

    # Materialize the new namespace completely before changing consumers or
    # removing logical originals. The caller builds in an isolated temporary
    # tree, so any later failure discards the entire candidate release.
    address_dir = output / ADDRESS_PREFIX
    temporary_dir = Path(tempfile.mkdtemp(prefix=".content-address.", dir=output))
    try:
        for output_path, body in sorted(finalized_bodies.items()):
            relative = PurePosixPath(output_path).relative_to(ADDRESS_PREFIX)
            destination = temporary_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
        temporary_dir.replace(address_dir)
    except BaseException:
        if temporary_dir.exists():
            for path in sorted(temporary_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            temporary_dir.rmdir()
        raise

    for path, body in rewritten.items():
        write_atomic(path, body)
    # Both the reachable candidates just finalized into `a/` (`mapping`) and
    # the unreachable candidates dropped from this release (`excluded`) have
    # their raw, un-addressed Zola output removed here: an excluded file left
    # at its logical path would still be served (uncached, unaddressed) and
    # would make public_files() see a physical file no manifest resource
    # covers, failing release_manifest.py's coverage check downstream.
    removed_logical = set(mapping) | excluded
    for logical_path in sorted(removed_logical):
        (output / logical_path).unlink()
    for directory in sorted(
        {path.parent for path in (output / logical for logical in removed_logical)},
        key=lambda value: len(value.parts),
        reverse=True,
    ):
        if directory != output:
            try:
                directory.rmdir()
            except OSError:
                pass

    resources = sorted(resources, key=lambda item: item["logical_path"])
    map_body = serialize_map(resources, media_types)
    write_atomic(map_path, map_body)
    return json.loads(map_body)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, help="built public tree to finalize")
    parser.add_argument("--map", dest="map_path", type=Path, required=True)
    parser.add_argument("--base-url", default=BASE_URL.rstrip("/"))
    parser.add_argument("--contract", type=Path, default=Path("release-resources.toml"))
    parser.add_argument("--retention-ledger", type=Path, default=RETENTION_LEDGER)
    parser.add_argument("--retention-assets", type=Path, default=RETENTION_ASSETS)
    parser.add_argument(
        "--record-retention-snapshot",
        action="store_true",
        help="explicitly append this release to the checked-in physical-asset ledger",
    )
    args = parser.parse_args()
    contract, errors = read_contract(args.contract)
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    try:
        document = finalize_tree(
            args.output,
            args.map_path,
            args.base_url,
            contract,
            retention_ledger=args.retention_ledger,
            retention_assets=args.retention_assets,
            record_retention_snapshot=args.record_retention_snapshot,
        )
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"ERROR: cannot content-address release: {exc}\n")
        return 1
    sys.stdout.write(
        f"PASS: content-addressed {document['resource_count']} resources with full SHA-256 paths\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
