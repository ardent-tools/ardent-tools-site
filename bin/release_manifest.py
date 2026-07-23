#!/usr/bin/env python3
"""Generate and validate the retained-tree release resource manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import stat
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}$")
OUTPUT_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
ADDRESSED_PATH_RE = re.compile(r"^a/([0-9a-f]{64})(\.[A-Za-z0-9]+)$")
MAX_RESOURCES = 1024
MANIFEST_SCHEMA_VERSION = 4
ASSET_MAP_SCHEMA_VERSION = 3
CONTRACT_PATH = Path("release-resources.toml")
BASE_URL = "https://ardent.tools/"
TEXT_URL_RE = re.compile(r"https://ardent\.tools/[^\s)\]>'\"]+")
HEADER_URL_RE = re.compile(r"[\"'](/[^\"']+)[\"']")
BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
BROWSER_URL_SCRIPT = r"""
const fs = require("node:fs");
const base = process.argv[1];
const inputs = JSON.parse(fs.readFileSync(0, "utf8"));
const resolved = inputs.map(({ reference, base, upgradeInsecure }) => {
  try {
    const url = new URL(reference, base);
    // Match the deployed `upgrade-insecure-requests` CSP before returning the
    // effective request identity. Mutating the URL also applies the standard's
    // port behavior (for example, authored http :443 becomes default HTTPS).
    if (upgradeInsecure && url.protocol === "http:") {
      url.protocol = "https:";
    }
    return {
      protocol: url.protocol,
      hostname: url.hostname,
      port: url.port,
      pathname: url.pathname,
      search: url.search,
      hash: url.hash,
    };
  } catch {
    return null;
  }
});
process.stdout.write(JSON.stringify(resolved));
"""
_UNRESOLVED = object()

SPECULATION_MEDIA_TYPE = "application/speculationrules+json"
SPECIAL_MEDIA_TYPES = {
    "speculation-rules.json": SPECULATION_MEDIA_TYPE,
}

# URL-valued HTML attributes are element-specific. Treating names such as
# `content` or `data` as URLs on every element corrupts ordinary metadata and
# literal custom data, so both finalization and validation share this registry.
HTML_URL_ATTRIBUTES_BY_TAG = {
    "a": frozenset({"href"}),
    "applet": frozenset({"code", "codebase"}),
    "area": frozenset({"href"}),
    "audio": frozenset({"src"}),
    "base": frozenset({"href"}),
    "bgsound": frozenset({"src"}),
    "blockquote": frozenset({"cite"}),
    "body": frozenset({"background"}),
    "button": frozenset({"formaction"}),
    "del": frozenset({"cite"}),
    "embed": frozenset({"src"}),
    "fencedframe": frozenset({"src"}),
    "form": frozenset({"action"}),
    "frame": frozenset({"longdesc", "src"}),
    "head": frozenset({"profile"}),
    "html": frozenset({"manifest"}),
    "iframe": frozenset({"src"}),
    "img": frozenset({"longdesc", "lowsrc", "src", "usemap"}),
    # The HTML parser's legacy image start-tag name is normalized to `img` by
    # browsers but remains `image` in Python's HTMLParser.
    "image": frozenset({"longdesc", "lowsrc", "src", "usemap"}),
    "input": frozenset({"formaction", "src", "usemap"}),
    "ins": frozenset({"cite"}),
    "link": frozenset({"href"}),
    "object": frozenset({"classid", "code", "codebase", "data", "usemap"}),
    "portal": frozenset({"src"}),
    "q": frozenset({"cite"}),
    "script": frozenset({"src"}),
    "source": frozenset({"src"}),
    "table": frozenset({"background"}),
    "td": frozenset({"background"}),
    "th": frozenset({"background"}),
    "tr": frozenset({"background"}),
    "track": frozenset({"src"}),
    "video": frozenset({"poster", "src"}),
}
META_URL_FIELDS = frozenset(
    {
        "og:audio",
        "og:audio:secure_url",
        "og:audio:url",
        "og:image",
        "og:image:secure_url",
        "og:image:url",
        "og:url",
        "og:video",
        "og:video:secure_url",
        "og:video:url",
        "twitter:app:url:googleplay",
        "twitter:app:url:ipad",
        "twitter:app:url:iphone",
        "twitter:image",
        "twitter:image:src",
        "twitter:player",
        "twitter:player:stream",
    }
)
PROJECT_URL_ATTRIBUTES = frozenset({"data-cast", "data-poster"})
JSON_LD_URL_FIELDS = frozenset(
    {
        "@context",
        "@id",
        "codeRepository",
        "contentUrl",
        "email",
        "image",
        "item",
        "knowsAbout",
        "license",
        "logo",
        "mainEntityOfPage",
        "sameAs",
        "subjectOf",
        "thumbnailUrl",
        "url",
    }
)


def html_url_attribute_names(
    tag: str, attrs: list[tuple[str, str | None]]
) -> frozenset[str]:
    """Return the URL-bearing fields for one concrete HTML element."""
    normalized_tag = tag.lower()
    names = set(HTML_URL_ATTRIBUTES_BY_TAG.get(normalized_tag, ()))
    names.update(PROJECT_URL_ATTRIBUTES)
    if normalized_tag == "meta":
        attributes = {
            name.lower(): (value or "") for name, value in attrs if name is not None
        }
        vocabulary = (
            (attributes.get("property") or attributes.get("name") or "").strip().lower()
        )
        if vocabulary in META_URL_FIELDS:
            names.add("content")
    return frozenset(names)


def json_ld_url_path(path: tuple[str | int, ...]) -> bool:
    """Whether a JSON-LD value path is URL-valued in the owned schemas."""
    if not path:
        return False
    if isinstance(path[-1], str):
        field = path[-1]
    elif len(path) >= 2:
        field = path[-2]
    else:
        return False
    return isinstance(field, str) and field in JSON_LD_URL_FIELDS


def webmanifest_url_path(path: tuple[str | int, ...]) -> bool:
    """Whether a Web App Manifest value path is URL-valued."""
    if path in {("id",), ("scope",), ("start_url",)}:
        return True
    patterns: tuple[tuple[object, ...], ...] = (
        ("icons", int, "src"),
        ("screenshots", int, "src"),
        ("shortcuts", int, "url"),
        ("shortcuts", int, "icons", int, "src"),
        ("share_target", "action"),
        ("protocol_handlers", int, "url"),
        ("file_handlers", int, "action"),
        ("related_applications", int, "url"),
        ("serviceworker", "src"),
        ("serviceworker", "scope"),
    )
    for pattern in patterns:
        if len(path) != len(pattern):
            continue
        if all(
            isinstance(part, expected) if expected is int else part == expected
            for part, expected in zip(path, pattern, strict=True)
        ):
            return True
    return False


def speculation_rules_url_path(path: tuple[str | int, ...]) -> bool:
    """Select list-source URLs, but never document-source URLPattern strings."""
    return (
        len(path) == 4
        and path[0] in {"prefetch", "prerender"}
        and isinstance(path[1], int)
        and path[2] == "urls"
        and isinstance(path[3], int)
    )


def selected_json_strings(
    value: object,
    selector,
    path: tuple[str | int, ...] = (),
) -> list[str]:
    """Collect strings selected by one owned JSON schema path predicate."""
    selected: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            selected.extend(selected_json_strings(child, selector, (*path, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            selected.extend(selected_json_strings(child, selector, (*path, index)))
    elif isinstance(value, str) and selector(path):
        selected.append(value)
    return selected


class ResourceReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        names = [name for name, _value in attrs]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            self.errors.append(f"duplicate HTML attributes are forbidden: {duplicates}")
        if tag in {"svg", "math"}:
            self.errors.append(
                f"inline {tag} foreign content is forbidden; use a retained external asset"
            )
        if tag == "base":
            self.errors.append(
                "base elements are forbidden; URL identity uses the document URL"
            )
        if tag == "meta" and any(
            name == "http-equiv" and (value or "").lower() == "refresh"
            for name, value in attrs
        ):
            self.errors.append(
                "meta refresh is forbidden; redirects belong in _redirects"
            )
        url_names = html_url_attribute_names(tag, attrs)
        for name, value in attrs:
            if (
                name
                in {
                    "archive",
                    "attributionsrc",
                    "imagesrcset",
                    "ping",
                    "srcdoc",
                    "srcset",
                }
                and value
            ):
                self.errors.append(
                    f"compound URL attribute {name!r} is forbidden until its grammar is validated"
                )
            elif name in url_names and value:
                if not value.startswith(("/", "#", "?")) and not SCHEME_RE.match(value):
                    self.errors.append(
                        f"relative URL attribute {name!r} is forbidden: {value!r}"
                    )
                self.references.append(value)


class JsonLdParser(HTMLParser):
    """Collect raw application/ld+json script bodies.

    Script content is CDATA to the HTML parser: character references are never
    decoded here, so the exact physical URL spelling remains directly inspectable.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._recording = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        media_type = (dict(attrs).get("type") or "").split(";", 1)[0].strip().lower()
        if tag == "script" and media_type == "application/ld+json":
            self._recording = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._recording:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._recording:
            self._recording = False
            self.blocks.append("".join(self._buffer))

    @property
    def unterminated(self) -> bool:
        return self._recording


def canonical_resource_path(path: str) -> str:
    """Decode and normalize a same-origin path for manifest-member identity.

    Percent-encoded spellings decode first (strict UTF-8, malformed
    sequences rejected), WHATWG-special backslashes are treated as path
    separators, and dot segments resolve via posixpath.normpath. An alias
    such as /img/%6cogo-flame.svg, /img\\logo-flame.svg, or
    /img/./logo-flame.svg therefore maps to the same member it tries to
    impersonate instead of bypassing the lookup.
    """
    if BAD_PERCENT_RE.search(path):
        raise ValueError(f"malformed percent-encoding in path {path!r}")
    decoded = unquote(path, encoding="utf-8", errors="strict").replace("\\", "/")
    normalized = posixpath.normpath(decoded)
    # POSIX intentionally preserves exactly two leading slashes, but the
    # deployed HTTP origin serves that spelling as the same retained path.
    if normalized.startswith("//"):
        normalized = f"/{normalized.lstrip('/')}"
    return normalized


def resolve_browser_references(
    references: list[str],
    bases: list[str] | None = None,
    *,
    upgrade_insecure: bool = True,
) -> list[dict[str, str] | None]:
    """Resolve authored URLs with the same WHATWG parser used by Node browsers.

    Python's RFC-oriented urllib parser intentionally differs at security-
    relevant boundaries including reverse solidus, excess authority slashes,
    C0 trimming, and IDNA host normalization. Node 22 is a pinned gate input,
    so one batched subprocess supplies the authoritative consumer parse rather
    than maintaining an inevitably incomplete second URL grammar here.
    """
    if not references:
        return []
    if bases is None:
        bases = [BASE_URL] * len(references)
    if len(bases) != len(references):
        raise ValueError("browser URL resolver requires one base per reference")
    inputs = [
        {
            "reference": reference,
            "base": base,
            "upgradeInsecure": upgrade_insecure,
        }
        for reference, base in zip(references, bases, strict=True)
    ]
    try:
        process = subprocess.run(
            ["node", "-e", BROWSER_URL_SCRIPT, BASE_URL],
            input=json.dumps(inputs),
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"cannot execute pinned Node URL parser: {exc}") from exc
    if process.returncode != 0:
        detail = process.stderr.strip() or f"exit {process.returncode}"
        raise ValueError(f"pinned Node URL parser failed: {detail}")
    try:
        document = json.loads(process.stdout)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(
            f"pinned Node URL parser returned invalid JSON: {exc}"
        ) from exc
    if not isinstance(document, list) or len(document) != len(references):
        raise ValueError("pinned Node URL parser returned the wrong result count")
    expected_keys = {"protocol", "hostname", "port", "pathname", "search", "hash"}
    for item in document:
        if item is None:
            continue
        if (
            not isinstance(item, dict)
            or set(item) != expected_keys
            or not all(isinstance(item[key], str) for key in expected_keys)
        ):
            raise ValueError("pinned Node URL parser returned a malformed result")
    return document


def css_reference_spans(
    raw: str, label: str, errors: list[str]
) -> list[tuple[int, int, str]]:
    """Return exact source spans for directly inspectable CSS url() targets.

    CSS escapes can obscure both the `url` function and its argument, so they
    are forbidden in retained CSS. Comments are skipped only while scanning
    ordinary CSS; inside url() they are literal URL bytes in Chromium and must
    remain visible to exact-identity checks. Imports and image-set are forbidden;
    with escapes excluded, the remaining url() grammar has no hidden continuation
    or quote rules.
    """
    if "\\" in raw:
        errors.append(
            f"{label}: CSS source contains a forbidden escape or backslash; "
            "resource syntax must remain directly inspectable"
        )
        return []
    source = raw
    references: list[tuple[int, int, str]] = []
    index = 0
    while index < len(source):
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                errors.append(f"{label}: CSS contains an unterminated comment")
                return []
            index = end + 2
            continue
        if source[index] in {"'", '"'}:
            quote = source[index]
            newline = min(
                (
                    position
                    for position in (
                        source.find("\n", index + 1),
                        source.find("\r", index + 1),
                        source.find("\f", index + 1),
                    )
                    if position >= 0
                ),
                default=-1,
            )
            end = source.find(quote, index + 1)
            if end < 0 or (newline >= 0 and newline < end):
                errors.append(
                    f"{label}: CSS contains an invalid or unterminated string"
                )
                return []
            index = end + 1
            continue
        if source[index : index + len("@import")].lower() == "@import":
            end = index + len("@import")
            if end == len(source) or not (source[end].isalnum() or source[end] in "_-"):
                errors.append(
                    f"{label}: CSS @import is forbidden; styles must be retained"
                )
                return []
        image_function = next(
            (
                name
                for name in ("image-set", "-webkit-image-set")
                if source[index : index + len(name)].lower() == name
            ),
            None,
        )
        if image_function is not None:
            cursor = index + len(image_function)
            while cursor < len(source) and source[cursor].isspace():
                cursor += 1
            if cursor < len(source) and source[cursor] == "(":
                errors.append(
                    f"{label}: CSS {image_function}() is forbidden until its grammar is validated"
                )
                return []
        if source[index : index + len("url")].lower() == "url" and (
            index == 0 or not (source[index - 1].isalnum() or source[index - 1] in "_-")
        ):
            cursor = index + 3
            while cursor < len(source) and source[cursor].isspace():
                cursor += 1
            if cursor < len(source) and source[cursor] == "(":
                cursor += 1
                while cursor < len(source) and source[cursor].isspace():
                    cursor += 1
                if cursor >= len(source):
                    errors.append(f"{label}: CSS contains an unterminated url()")
                    return []
                if source[cursor] in {"'", '"'}:
                    quote = source[cursor]
                    end = source.find(quote, cursor + 1)
                    if end < 0 or any(
                        char in source[cursor + 1 : end] for char in "\n\r\f"
                    ):
                        errors.append(f"{label}: CSS contains an invalid url() string")
                        return []
                    reference = source[cursor + 1 : end]
                    reference_start = cursor + 1
                    reference_end = end
                    closing = end + 1
                    while closing < len(source) and source[closing].isspace():
                        closing += 1
                    if closing >= len(source) or source[closing] != ")":
                        errors.append(f"{label}: CSS contains a malformed url()")
                        return []
                else:
                    closing = source.find(")", cursor)
                    if closing < 0:
                        errors.append(f"{label}: CSS contains an unterminated url()")
                        return []
                    untrimmed = source[cursor:closing]
                    reference = untrimmed.strip()
                    reference_start = cursor + (
                        len(untrimmed) - len(untrimmed.lstrip())
                    )
                    reference_end = closing - (len(untrimmed) - len(untrimmed.rstrip()))
                    if any(char in reference for char in "'\""):
                        errors.append(f"{label}: CSS contains a malformed url()")
                        return []
                if (
                    reference
                    and not reference.startswith(("/", "#", "?"))
                    and not SCHEME_RE.match(reference)
                ):
                    errors.append(
                        f"{label}: path-relative CSS url() is forbidden: {reference!r}"
                    )
                    return []
                references.append((reference_start, reference_end, reference))
                index = closing + 1
                continue
        index += 1
    return references


def css_references(raw: str, label: str, errors: list[str]) -> list[str]:
    """Return the URL values from :func:`css_reference_spans`."""
    return [
        reference for _start, _end, reference in css_reference_spans(raw, label, errors)
    ]


def validate_svg_files(output: Path) -> list[str]:
    """Require retained SVG images to remain strict and self-contained.

    An SVG served as a top-level document can initiate subresource requests.
    The site has no need for that capability: external URLs, active/foreign
    content, and URL animation are forbidden, while local fragment references
    used by definitions and filters remain valid.
    """
    errors: list[str] = []
    svg_namespace = "http://www.w3.org/2000/svg"
    forbidden_elements = {
        "animate",
        "animateMotion",
        "animateTransform",
        "discard",
        "foreignObject",
        "script",
        "set",
    }
    for path in sorted(output.rglob("*.svg")):
        label = str(path.relative_to(output))
        try:
            raw = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{label}: SVG is not strict UTF-8: {exc}")
            continue
        xml_body = raw.removeprefix("\ufeff")
        declaration = re.match(r"<\?xml\s[^?]*\?>", xml_body, re.I)
        if declaration is not None:
            xml_body = xml_body[declaration.end() :]
        if "<?" in xml_body:
            errors.append(f"{label}: SVG processing instructions are forbidden")
            continue
        if "<!DOCTYPE" in raw.upper():
            errors.append(f"{label}: SVG document types are forbidden")
            continue
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            errors.append(f"{label}: SVG is not strict XML: {exc}")
            continue
        if root.tag != f"{{{svg_namespace}}}svg":
            errors.append(
                f"{label}: retained .svg root must use the canonical SVG namespace"
            )
            continue
        for element in root.iter():
            if not element.tag.startswith(f"{{{svg_namespace}}}"):
                errors.append(f"{label}: foreign-namespace SVG elements are forbidden")
                continue
            element_name = element.tag.removeprefix(f"{{{svg_namespace}}}")
            if element_name in forbidden_elements:
                errors.append(f"{label}: SVG element {element_name!r} is forbidden")
            if element_name == "style":
                # Chromium derives SVG style data from textContent, which also
                # includes the tails of child elements. Keep the accepted XML
                # grammar narrower so no CSS can hide outside element.text.
                if len(element):
                    errors.append(f"{label}: SVG style elements must not have children")
                elif element.text:
                    style_errors: list[str] = []
                    for reference in css_references(element.text, label, style_errors):
                        if not reference.lstrip("\t\n\r ").startswith("#"):
                            errors.append(
                                f"{label}: SVG styles must not load external "
                                f"resource {reference!r}"
                            )
                    errors.extend(style_errors)
            for raw_name, value in element.attrib.items():
                name = raw_name.rsplit("}", 1)[-1]
                if "\\" in value:
                    errors.append(
                        f"{label}: SVG attribute {name!r} contains a forbidden "
                        "escape or backslash"
                    )
                    continue
                if name.lower().startswith("on"):
                    errors.append(f"{label}: SVG event attribute {name!r} is forbidden")
                if name in {"base", "href"} and value and not value.startswith("#"):
                    errors.append(
                        f"{label}: SVG attribute {name!r} must be a local fragment"
                    )
                if "url(" in value.lower() or name == "style":
                    style_errors = []
                    for reference in css_references(value, label, style_errors):
                        if not reference.lstrip("\t\n\r ").startswith("#"):
                            errors.append(
                                f"{label}: SVG attribute {name!r} must not load "
                                f"external resource {reference!r}"
                            )
                    errors.extend(style_errors)
    return errors


def inspect_manifest_reference(
    errors: list[str],
    label: str,
    reference: str,
    by_path: dict[str, str],
    resolved: dict[str, str] | None | object = _UNRESOLVED,
) -> None:
    """Fail when a same-origin reference spells a manifest member inexactly.

    The reference resolves through the browser's WHATWG URL implementation for
    member lookup, but only the exact root-relative manifest URL or its exact
    HTTPS absolute spelling is accepted. HTTP references to the canonical host
    are also examined because the deployed CSP upgrades them before fetch.
    """
    # Fragment-only strings do not initiate a resource request. This also
    # distinguishes webmanifest color values such as "#F7F3E8" from URLs.
    # Query-only references are intentionally inspected: in CSS they refetch
    # the stylesheet itself under a different, non-manifest identity.
    if reference.lstrip("\t\n\r ").startswith("#"):
        return
    if resolved is _UNRESOLVED:
        try:
            resolved = resolve_browser_references([reference])[0]
        except ValueError as exc:
            errors.append(f"{label}: browser URL resolution failed closed: {exc}")
            return
    if resolved is None:
        return
    assert isinstance(resolved, dict)
    base_host = urlparse(BASE_URL).hostname
    is_effective_site_origin = (
        resolved["protocol"] == "https:"
        and resolved["hostname"] == base_host
        and resolved["port"] == ""
    )
    if not is_effective_site_origin:
        return
    try:
        canonical_path = canonical_resource_path(resolved["pathname"])
    except (UnicodeDecodeError, ValueError) as exc:
        errors.append(f"{label}: noncanonical resource path in {reference!r}: {exc}")
        return
    expected = by_path.get(canonical_path)
    if expected is None:
        return
    accepted = {expected, f"{BASE_URL.rstrip('/')}{expected}"}
    if reference not in accepted:
        errors.append(
            f"{label}: public resource {reference!r} must use manifest URL {expected!r}"
        )


def strict_json_loads(
    raw: str,
    label: str,
    errors: list[str],
    *,
    kind: str = "application/ld+json",
) -> object | None:
    """Parse one JSON document, rejecting extensions and duplicate keys."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-JSON constant {value!r}")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            raw, parse_constant=reject_constant, object_pairs_hook=reject_duplicates
        )
    except (ValueError, RecursionError) as exc:
        errors.append(f"{label}: {kind} is not strict JSON: {exc}")
        return None


def json_ld_references(errors: list[str], label: str, raw: str) -> list[str]:
    """Strict-parse one JSON-LD block and return schema URL fields only."""
    document = strict_json_loads(raw, label, errors)
    if document is None:
        return []
    return selected_json_strings(document, json_ld_url_path)


def read_contract(path: Path = CONTRACT_PATH) -> tuple[dict, list[str]]:
    errors: list[str] = []
    try:
        contract = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {}, [f"{path}: cannot read release contract: {exc}"]
    if set(contract) != {
        "schema_version",
        "manifest_name",
        "canonical_paths",
        "tombstones",
    }:
        errors.append(f"{path}: release contract has unexpected or missing keys")
    if contract.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(f"{path}: schema_version must be {MANIFEST_SCHEMA_VERSION}")
    manifest_name = contract.get("manifest_name")
    if manifest_name != "release-resources.json":
        errors.append(f"{path}: manifest_name must be 'release-resources.json'")
    canonical = contract.get("canonical_paths")
    if not isinstance(canonical, list) or not canonical:
        errors.append(f"{path}: canonical_paths must be a nonempty array")
    elif len(canonical) != len(set(canonical)):
        errors.append(f"{path}: canonical_paths contains duplicates")
    else:
        for value in canonical:
            if not valid_output_path(value):
                errors.append(f"{path}: invalid canonical path {value!r}")
    tombstones = contract.get("tombstones")
    if not isinstance(tombstones, list) or not tombstones:
        errors.append(f"{path}: tombstones must be a nonempty array")
    else:
        seen: set[str] = set()
        for item in tombstones:
            if not isinstance(item, dict) or set(item) != {
                "path",
                "retain_through",
                "reason",
            }:
                errors.append(
                    f"{path}: each tombstone must have path, retain_through, and reason"
                )
                continue
            tombstone_path = item.get("path")
            if not isinstance(tombstone_path, str) or not valid_request_path(
                tombstone_path
            ):
                errors.append(f"{path}: invalid tombstone path {tombstone_path!r}")
            elif tombstone_path in seen:
                errors.append(f"{path}: duplicate tombstone path {tombstone_path!r}")
            else:
                seen.add(tombstone_path)
            if not isinstance(item.get("retain_through"), str) or not DATE_RE.fullmatch(
                item["retain_through"]
            ):
                errors.append(f"{path}: tombstone retain_through must be YYYY-MM-DD")
            if not isinstance(item.get("reason"), str) or not item["reason"].strip():
                errors.append(f"{path}: tombstone reason must be nonempty")
    return contract, errors


def valid_output_path(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith(("/", "."))
        or not OUTPUT_PATH_RE.fullmatch(value)
    ):
        return False
    if "\\" in value or "//" in value:
        return False
    path = PurePosixPath(value)
    return all(part not in {"", ".", ".."} for part in path.parts)


def valid_request_path(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
    ):
        return False
    parsed = urlparse(value)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or "\\" in parsed.path
    ):
        return False
    return valid_output_path(parsed.path.lstrip("/"))


def public_files(output: Path, manifest_name: str) -> list[Path]:
    files: list[Path] = []
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise ValueError(
                f"public artifact must not be a symlink: {path.relative_to(output)}"
            )
        if not path.exists() or not stat.S_ISREG(path.lstat().st_mode):
            continue
        relative = path.relative_to(output).as_posix()
        if relative in {
            "_headers",
            "_redirects",
            "_routes.json",
            manifest_name,
        } or relative.endswith(".html"):
            continue
        files.append(path)
    return files


def read_asset_map(path: Path) -> tuple[dict, list[str]]:
    errors: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        return {}, [f"asset map cannot be read as strict UTF-8: {exc}"]
    document = strict_json_loads(raw, "asset map", errors, kind="document")
    if not isinstance(document, dict):
        return {}, errors or ["asset map root must be an object"]
    if set(document) != {
        "schema_version",
        "resource_count",
        "resources",
        "media_types",
    }:
        errors.append("asset map has unexpected or missing top-level keys")
        return document, errors
    if document.get("schema_version") != ASSET_MAP_SCHEMA_VERSION:
        errors.append(f"asset map schema_version must be {ASSET_MAP_SCHEMA_VERSION}")
    resources = document.get("resources")
    if not isinstance(resources, list):
        errors.append("asset map resources must be an array")
        return document, errors
    if document.get("resource_count") != len(resources):
        errors.append("asset map resource_count does not equal resources length")
    seen_logical: set[str] = set()
    seen_output: set[str] = set()
    request_urls: set[str] = set()
    required_media_types: dict[str, str] = {}
    for index, item in enumerate(resources):
        label = f"asset map resources[{index}]"
        expected_keys = {
            "logical_path",
            "output_path",
            "request_url",
            "sha256",
            "cache_class",
        }
        if not isinstance(item, dict) or set(item) != expected_keys:
            errors.append(f"{label} must contain only {sorted(expected_keys)}")
            continue
        logical = item.get("logical_path")
        output_path = item.get("output_path")
        request = item.get("request_url")
        digest = item.get("sha256")
        cache_class = item.get("cache_class")
        if not valid_output_path(logical):
            errors.append(f"{label} has invalid logical_path {logical!r}")
        elif cache_class == "addressed" and logical.startswith("a/"):
            errors.append(f"{label} addressed logical_path uses the physical namespace")
        elif cache_class == "retained" and logical != output_path:
            errors.append(f"{label} retained logical_path must equal output_path")
        elif cache_class not in {"addressed", "retained"}:
            errors.append(f"{label} has invalid cache_class {cache_class!r}")
        elif logical in seen_logical:
            errors.append(f"asset map repeats logical_path {logical!r}")
        else:
            seen_logical.add(logical)
        if not valid_output_path(output_path):
            errors.append(f"{label} has invalid output_path {output_path!r}")
            continue
        if output_path in seen_output:
            errors.append(f"asset map repeats output_path {output_path!r}")
        seen_output.add(output_path)
        match = ADDRESSED_PATH_RE.fullmatch(output_path)
        if match is None:
            errors.append(f"{label} output_path is not a full-digest physical path")
        elif (
            cache_class == "addressed"
            and isinstance(logical, str)
            and (PurePosixPath(logical).suffix.lower() != match.group(2).lower())
        ):
            errors.append(f"{label} physical extension differs from logical_path")
        if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
            errors.append(f"{label} has malformed sha256 {digest!r}")
        elif match is not None and match.group(1) != digest:
            errors.append(f"{label} filename digest differs from sha256")
        if request != f"/{output_path}":
            errors.append(f"{label} request_url must be exactly '/{output_path}'")
        elif isinstance(request, str):
            request_urls.add(request)
            special = (
                SPECIAL_MEDIA_TYPES.get(logical) if isinstance(logical, str) else None
            )
            if special is not None:
                required_media_types[request] = special
    media_types = document.get("media_types")
    if not isinstance(media_types, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in (media_types.items() if isinstance(media_types, dict) else ())
    ):
        errors.append("asset map media_types must be a string-to-string object")
    else:
        if list(media_types) != sorted(media_types):
            errors.append("asset map media_types must be sorted by request URL")
        for request_url, media_type in media_types.items():
            if request_url not in request_urls:
                errors.append(
                    f"asset map media_types names an absent resource: {request_url!r}"
                )
            if media_type not in SPECIAL_MEDIA_TYPES.values():
                errors.append(
                    f"asset map media_types has unsupported value {media_type!r}"
                )
        for request_url, media_type in required_media_types.items():
            if media_types.get(request_url) != media_type:
                errors.append(
                    f"asset map lacks required media type for {request_url!r}"
                )
    return document, errors


def build_manifest(
    output: Path, revision: str, asset_map: dict, contract: dict
) -> dict:
    if not REVISION_RE.fullmatch(revision):
        raise ValueError("revision must be exactly one lowercase 40-hex value")
    manifest_name = contract["manifest_name"]
    canonical = set(contract["canonical_paths"])
    resources: list[dict[str, str]] = []
    physical_files = {
        path.relative_to(output).as_posix(): path
        for path in public_files(output, manifest_name)
    }
    for relative in sorted(canonical):
        path = physical_files.get(relative)
        if path is None:
            raise ValueError(f"canonical resource is absent: {relative}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        resources.append(
            {
                "logical_path": relative,
                "output_path": relative,
                "request_url": f"/{relative}",
                "sha256": digest,
                "cache_class": "canonical",
            }
        )
    for mapped in asset_map.get("resources", []):
        relative = mapped["output_path"]
        path = physical_files.get(relative)
        if path is None:
            raise ValueError(f"addressed resource is absent: {relative}")
        relative = path.relative_to(output).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != mapped["sha256"]:
            raise ValueError(
                f"addressed resource digest differs from asset map: {relative}"
            )
        resources.append(
            {
                "logical_path": mapped["logical_path"],
                "output_path": relative,
                "request_url": f"/{relative}",
                "sha256": digest,
                "cache_class": mapped["cache_class"],
            }
        )
    resources.sort(key=lambda item: item["logical_path"])
    covered = {item["output_path"] for item in resources}
    if covered != set(physical_files):
        raise ValueError(
            "asset map and canonical contract do not cover retained resources; "
            f"missing={sorted(set(physical_files) - covered)}, "
            f"extra={sorted(covered - set(physical_files))}"
        )
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "revision": revision,
        "resource_count": len(resources),
        "resources": resources,
        "media_types": asset_map["media_types"],
        "tombstones": contract["tombstones"],
    }


def serialize_manifest(manifest: dict) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_public_references(output: Path, manifest: dict) -> list[str]:
    """Require every authored reference to a manifest member to use its exact URL.

    Coverage: HTML URL attributes (entity-decoded by the parser, with compound
    URL grammars and document-base overrides rejected), every string inside
    owned URL-valued fields in each application/ld+json block (strict JSON,
    raw text), CSS url() targets
    (with escapes, imports, and image-set rejected), self-contained strict SVG,
    site.webmanifest JSON strings, agent-facing text files, and _headers values.
    """
    errors: list[str] = []
    by_path: dict[str, str] = {}
    for item in manifest.get("resources", []):
        if not isinstance(item, dict) or not isinstance(item.get("request_url"), str):
            continue
        for key in ("logical_path", "output_path"):
            value = item.get(key)
            if isinstance(value, str):
                by_path[f"/{value}"] = item["request_url"]
    references: list[tuple[str, str, str]] = []

    for path in sorted(output.rglob("*.html")):
        text = path.read_text()
        label = str(path.relative_to(output))
        parser = ResourceReferenceParser()
        parser.feed(text)
        parser.close()
        errors.extend(f"{label}: {error}" for error in parser.errors)
        if label == "index.html":
            document_url = BASE_URL
        elif label.endswith("/index.html"):
            document_url = f"{BASE_URL}{label.removesuffix('index.html')}"
        else:
            document_url = f"{BASE_URL}{label}"
        for reference in parser.references:
            references.append((label, reference, document_url))
        ld_parser = JsonLdParser()
        ld_parser.feed(text)
        ld_parser.close()
        if ld_parser.unterminated:
            errors.append(f"{label}: unterminated application/ld+json block")
        for block in ld_parser.blocks:
            references.extend(
                (label, reference, document_url)
                for reference in json_ld_references(errors, label, block)
            )
    for path in sorted(output.rglob("*.css")):
        label = str(path.relative_to(output))
        css = path.read_text()
        references.extend(
            (label, reference, f"{BASE_URL}{label}")
            for reference in css_references(css, label, errors)
        )
    errors.extend(validate_svg_files(output))
    for logical_path, selector in (
        ("site.webmanifest", webmanifest_url_path),
        ("speculation-rules.json", speculation_rules_url_path),
    ):
        items = [
            item
            for item in manifest.get("resources", [])
            if isinstance(item, dict) and item.get("logical_path") == logical_path
        ]
        if len(items) != 1:
            errors.append(
                f"{logical_path}: release manifest must contain exactly one logical resource"
            )
            continue
        item = items[0]
        document = strict_json_loads(
            (output / item["output_path"]).read_text(),
            logical_path,
            errors,
            kind="document",
        )
        if document is None:
            continue
        for value in selected_json_strings(document, selector):
            if (
                value
                and not value.startswith(("/", "#", "?"))
                and not SCHEME_RE.match(value)
            ):
                errors.append(
                    f"{logical_path}: path-relative JSON URL field is forbidden: {value!r}"
                )
                continue
            references.append((logical_path, value, f"{BASE_URL}{item['output_path']}"))
    for relative in ("llms.txt", "robots.txt"):
        path = output / relative
        if path.is_file():
            for match in TEXT_URL_RE.finditer(path.read_text()):
                references.append((relative, match.group(0), f"{BASE_URL}{relative}"))
    headers = output / "_headers"
    if headers.is_file():
        for match in HEADER_URL_RE.finditer(headers.read_text()):
            references.append(("_headers", match.group(1), BASE_URL))
    try:
        resolved = resolve_browser_references(
            [reference for _label, reference, _base in references],
            [base for _label, _reference, base in references],
        )
    except ValueError as exc:
        errors.append(f"browser URL resolution failed closed: {exc}")
        return errors
    for (label, reference, _base), browser_url in zip(
        references, resolved, strict=True
    ):
        inspect_manifest_reference(errors, label, reference, by_path, browser_url)
    return errors


def validate_manifest(
    raw: bytes,
    *,
    output: Path,
    expected_revision: str,
    contract: dict,
) -> tuple[dict, list[str]]:
    errors: list[str] = []
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return {}, [f"release manifest is not strict UTF-8 JSON: {exc}"]
    manifest = strict_json_loads(
        text,
        "release manifest",
        errors,
        kind="document",
    )
    if manifest is None:
        return {}, errors
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "revision",
        "resource_count",
        "resources",
        "media_types",
        "tombstones",
    }:
        return {}, ["release manifest has unexpected or missing top-level keys"]
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(
            f"release manifest schema_version must be {MANIFEST_SCHEMA_VERSION}"
        )
    if manifest.get("revision") != expected_revision:
        errors.append(
            f"release manifest revision mismatch: expected {expected_revision}, "
            f"found {manifest.get('revision')!r}"
        )
    resources = manifest.get("resources")
    if not isinstance(resources, list):
        return manifest, errors + ["release manifest resources must be an array"]
    if not 1 <= len(resources) <= MAX_RESOURCES:
        errors.append(
            f"release manifest resource count {len(resources)} is outside 1..{MAX_RESOURCES}"
        )
    if (
        not isinstance(manifest.get("resource_count"), int)
        or isinstance(manifest.get("resource_count"), bool)
        or manifest["resource_count"] != len(resources)
    ):
        errors.append("release manifest resource_count does not equal resources length")
    manifest_name = contract["manifest_name"]
    canonical = set(contract["canonical_paths"])
    expected_paths: set[str]
    try:
        expected_paths = {
            path.relative_to(output).as_posix()
            for path in public_files(output, manifest_name)
        }
    except ValueError as exc:
        errors.append(str(exc))
        expected_paths = set()
    seen_paths: set[str] = set()
    seen_logical: set[str] = set()
    seen_urls: set[str] = set()
    required_media_types: dict[str, str] = {}
    for index, item in enumerate(resources):
        label = f"release manifest resources[{index}]"
        expected_keys = {
            "logical_path",
            "request_url",
            "output_path",
            "sha256",
            "cache_class",
        }
        if not isinstance(item, dict) or set(item) != expected_keys:
            errors.append(f"{label} must contain only {sorted(expected_keys)}")
            continue
        logical_path = item.get("logical_path")
        output_path = item.get("output_path")
        url = item.get("request_url")
        digest = item.get("sha256")
        cache_class = item.get("cache_class")
        if not valid_output_path(logical_path):
            errors.append(f"{label} has invalid logical_path {logical_path!r}")
            continue
        if logical_path in seen_logical:
            errors.append(f"release manifest repeats logical_path {logical_path!r}")
        seen_logical.add(logical_path)
        if not valid_output_path(output_path):
            errors.append(f"{label} has invalid output_path {output_path!r}")
            continue
        if output_path in seen_paths:
            errors.append(f"release manifest repeats output_path {output_path!r}")
        seen_paths.add(output_path)
        if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
            errors.append(f"{label} has malformed sha256 {digest!r}")
            continue
        if not isinstance(url, str) or url in seen_urls:
            errors.append(f"{label} has missing or duplicate request_url {url!r}")
        else:
            seen_urls.add(url)
            special = (
                SPECIAL_MEDIA_TYPES.get(logical_path)
                if isinstance(logical_path, str)
                else None
            )
            if special is not None:
                required_media_types[url] = special
        expected_url = f"/{output_path}"
        if url != expected_url:
            errors.append(
                f"{label} request_url must be {expected_url!r}, found {url!r}"
            )
        if cache_class == "canonical":
            if logical_path != output_path or output_path not in canonical:
                errors.append(
                    f"{label} canonical identity differs from release contract"
                )
        elif cache_class in {"addressed", "retained"}:
            match = ADDRESSED_PATH_RE.fullmatch(output_path)
            if match is None:
                errors.append(f"{label} is not a full-digest physical path")
            elif match.group(1) != digest:
                errors.append(f"{label} filename digest differs from sha256")
            elif cache_class == "addressed" and (
                PurePosixPath(logical_path).suffix.lower() != match.group(2).lower()
            ):
                errors.append(f"{label} physical extension differs from logical_path")
            if cache_class == "addressed" and (
                logical_path in canonical or logical_path == output_path
            ):
                errors.append(f"{label} has an invalid addressed logical identity")
            if cache_class == "retained" and logical_path != output_path:
                errors.append(f"{label} has an invalid retained physical identity")
            logical_artifact = output / logical_path
            if cache_class == "addressed" and (
                logical_artifact.exists() or logical_artifact.is_symlink()
            ):
                errors.append(
                    f"{label} logical alias survives in retained artifact: {logical_path}"
                )
        else:
            errors.append(f"{label} has invalid cache_class {cache_class!r}")
        artifact = output / output_path
        try:
            artifact.relative_to(output)
        except ValueError:
            errors.append(f"{label} escapes the retained artifact root")
            continue
        if not artifact.is_file() or artifact.is_symlink():
            errors.append(f"{label} does not resolve to a regular retained artifact")
        elif hashlib.sha256(artifact.read_bytes()).hexdigest() != digest:
            errors.append(f"{label} sha256 does not match retained artifact bytes")
    media_types = manifest.get("media_types")
    if not isinstance(media_types, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in (media_types.items() if isinstance(media_types, dict) else ())
    ):
        errors.append("release manifest media_types must be a string-to-string object")
    else:
        if list(media_types) != sorted(media_types):
            errors.append("release manifest media_types must be sorted by request URL")
        for request_url, media_type in media_types.items():
            if request_url not in seen_urls:
                errors.append(
                    f"release manifest media_types names an absent resource: {request_url!r}"
                )
            if media_type not in SPECIAL_MEDIA_TYPES.values():
                errors.append(
                    f"release manifest media_types has unsupported value {media_type!r}"
                )
        for request_url, media_type in required_media_types.items():
            if media_types.get(request_url) != media_type:
                errors.append(
                    f"release manifest lacks required media type for {request_url!r}"
                )
    if seen_paths != expected_paths:
        missing = sorted(expected_paths - seen_paths)
        extra = sorted(seen_paths - expected_paths)
        errors.append(
            f"release manifest coverage differs; missing={missing}, extra={extra}"
        )
    missing_canonical = sorted(canonical - expected_paths)
    if missing_canonical:
        errors.append(
            f"release contract canonical paths are absent: {missing_canonical}"
        )
    tombstones = manifest.get("tombstones")
    if tombstones != contract["tombstones"]:
        errors.append("release manifest tombstones differ from release-resources.toml")
    for item in tombstones if isinstance(tombstones, list) else []:
        path = item.get("path") if isinstance(item, dict) else None
        if isinstance(path, str) and (
            path.lstrip("/") in expected_paths or path.lstrip("/") in seen_logical
        ):
            errors.append(f"tombstone is present in retained artifact: {path}")
    return manifest, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, help="already-built retained public tree")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--asset-map", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    args = parser.parse_args()
    contract, errors = read_contract(args.contract)
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    asset_map, map_errors = read_asset_map(args.asset_map)
    if map_errors:
        for error in map_errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    try:
        manifest = build_manifest(
            args.output.resolve(), args.revision, asset_map, contract
        )
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"ERROR: cannot generate release manifest: {exc}\n")
        return 1
    destination = args.output / contract["manifest_name"]
    destination.write_bytes(serialize_manifest(manifest))
    _, errors = validate_manifest(
        destination.read_bytes(),
        output=args.output.resolve(),
        expected_revision=args.revision,
        contract=contract,
    )
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    sys.stdout.write(
        f"PASS: release manifest covers {manifest['resource_count']} served non-HTML resources\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
