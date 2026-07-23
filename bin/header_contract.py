#!/usr/bin/env python3
"""Exact Cloudflare Pages header contract for retained and live output."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from pages_limits import MAX_HEADER_RULES, require_media_type_rule_capacity
from release_manifest import SPECIAL_MEDIA_TYPES, SPECULATION_MEDIA_TYPE

ROOT_PATH = "/*"
ADDRESSED_ASSET_PATH = "/a/*"

# Every non-HTML resource is served at /a/<full-sha256>.<ext>, provably
# immutable by construction (content_address.py content-addresses the path
# itself), so it carries a long-lived immutable policy instead of the root
# no-store default. Cloudflare Pages joins same-name headers from
# overlapping sections with a comma rather than letting the later section
# override the earlier one, so this section's Cache-Control cannot simply
# coexist with /*'s — it must detach the inherited value first (see the `!`
# line in _headers); validate_headers() requires that detach explicitly.
ADDRESSED_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
ADDRESSED_ASSET_HEADERS = {"cache-control": ADDRESSED_ASSET_CACHE_CONTROL}

DIRECT_RESPONSE_HEADERS = {
    "cache-control": "no-store, no-transform",
    "strict-transport-security": "max-age=31536000; includeSubDomains; preload",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": (
        "accelerometer=(), browsing-topics=(), camera=(), clipboard-read=(), "
        "clipboard-write=(), geolocation=(), gyroscope=(), hid=(), "
        "magnetometer=(), microphone=(), midi=(), payment=(), serial=(), "
        "usb=(), web-share=(), xr-spatial-tracking=()"
    ),
    "content-security-policy": (
        "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; "
        "font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'self'; "
        "frame-ancestors 'none'; object-src 'none'; manifest-src 'self'; "
        "worker-src 'none'; upgrade-insecure-requests"
    ),
}


class HeaderContract(NamedTuple):
    direct_response: dict[str, str]
    speculation_content_type: str
    media_types: dict[str, str]


def manifest_request_url(manifest: dict, logical_path: str) -> str | None:
    matches = [
        item.get("request_url")
        for item in manifest.get("resources", [])
        if isinstance(item, dict) and item.get("logical_path") == logical_path
    ]
    if len(matches) != 1 or not isinstance(matches[0], str):
        return None
    return matches[0]


def expected_contract(manifest: dict) -> tuple[HeaderContract | None, list[str]]:
    speculation_url = manifest_request_url(manifest, "speculation-rules.json")
    if speculation_url is None:
        return None, [
            "_headers: release manifest must contain exactly one speculation-rules.json resource"
        ]
    direct = dict(DIRECT_RESPONSE_HEADERS)
    direct["speculation-rules"] = f'"{speculation_url}"'
    media_types = manifest.get("media_types")
    if not isinstance(media_types, dict) or any(
        not isinstance(path, str) or not isinstance(media_type, str)
        for path, media_type in (
            media_types.items() if isinstance(media_types, dict) else ()
        )
    ):
        return None, ["_headers: release manifest media_types is invalid"]
    if media_types.get(speculation_url) != SPECULATION_MEDIA_TYPE:
        return None, [
            "_headers: current speculation-rules resource lacks its exact media type"
        ]
    if any(
        media_type not in SPECIAL_MEDIA_TYPES.values()
        for media_type in media_types.values()
    ):
        return None, ["_headers: release manifest carries an unsupported media type"]
    try:
        require_media_type_rule_capacity(len(media_types))
    except ValueError as exc:
        return None, [str(exc)]
    return HeaderContract(
        direct,
        SPECULATION_MEDIA_TYPE,
        dict(sorted(media_types.items())),
    ), []


def parse_headers(
    raw: str,
) -> tuple[dict[str, dict[str, str]], dict[str, frozenset[str]], list[str]]:
    """Parse each section to its own resulting header map, independent of any
    other section (this contract never simulates Cloudflare's cross-section
    join — see validate-site.py's effective_headers() for that live
    simulation). A `! Header-Name` detach line removes that key from the
    section-in-progress; `detached` separately records which names were ever
    detached per section, since a detach that is never followed by a reset
    resolves to the same missing-key shape as one that never happened at all
    — callers that require a detach (e.g. a section overriding an inherited
    value) must check `detached`, not just the resulting flat map.
    """
    sections: dict[str, dict[str, str]] = {}
    detached: dict[str, set[str]] = {}
    errors: list[str] = []
    current_path: str | None = None
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw_line[0].isspace():
            if any(character.isspace() for character in stripped):
                errors.append(
                    f"_headers:{line_number}: path declaration contains whitespace: {stripped!r}"
                )
                current_path = None
                continue
            if not stripped.startswith("/"):
                errors.append(
                    f"_headers:{line_number}: path declaration must be same-origin: {stripped!r}"
                )
                current_path = None
                continue
            if stripped in sections:
                errors.append(
                    f"_headers:{line_number}: duplicate path declaration {stripped!r}"
                )
                current_path = None
                continue
            current_path = stripped
            sections[current_path] = {}
            detached[current_path] = set()
            continue

        if current_path is None:
            errors.append(
                f"_headers:{line_number}: header has no valid path declaration"
            )
            continue
        if stripped.startswith("! "):
            detach_name = stripped[2:].strip().lower()
            if not detach_name:
                errors.append(
                    f"_headers:{line_number}: detach operation names no header"
                )
                continue
            sections[current_path].pop(detach_name, None)
            detached[current_path].add(detach_name)
            continue
        if ":" not in stripped:
            errors.append(
                f"_headers:{line_number}: malformed header declaration {stripped!r}"
            )
            continue
        name, value = stripped.split(":", 1)
        normalized_name = name.strip().lower()
        normalized_value = value.strip()
        if not normalized_name or not normalized_value:
            errors.append(f"_headers:{line_number}: empty header name or value")
            continue
        section = sections[current_path]
        if normalized_name in section:
            errors.append(
                f"_headers:{line_number}: duplicate {normalized_name!r} in {current_path!r}"
            )
            continue
        section[normalized_name] = normalized_value
    return sections, {path: frozenset(names) for path, names in detached.items()}, errors


def validate_headers(
    raw: str, manifest: dict
) -> tuple[HeaderContract | None, list[str]]:
    contract, errors = expected_contract(manifest)
    sections, detached, parse_errors = parse_headers(raw)
    errors.extend(parse_errors)
    if len(sections) > MAX_HEADER_RULES:
        errors.append(
            f"_headers contains {len(sections)} rules; Cloudflare Pages permits "
            f"at most {MAX_HEADER_RULES}"
        )
    if contract is None:
        return None, errors
    expected_sections = {
        ROOT_PATH: contract.direct_response,
        ADDRESSED_ASSET_PATH: ADDRESSED_ASSET_HEADERS,
        **{
            path: {"content-type": media_type}
            for path, media_type in contract.media_types.items()
        },
    }
    if set(sections) != set(expected_sections):
        errors.append(
            "_headers: supported path set differs; "
            f"expected={sorted(expected_sections)}, found={sorted(sections)}"
        )
    for path, expected in expected_sections.items():
        actual = sections.get(path)
        if actual is not None and actual != expected:
            errors.append(
                f"_headers: {path} header map differs; expected={expected!r}, found={actual!r}"
            )
    if "cache-control" not in detached.get(ADDRESSED_ASSET_PATH, frozenset()):
        errors.append(
            f"_headers: {ADDRESSED_ASSET_PATH!r} must detach the inherited "
            "cache-control header (`! Cache-Control`) before declaring its "
            "own — Cloudflare Pages joins same-name headers from overlapping "
            "sections rather than letting the later one win"
        )
    return contract, errors


def load_headers(path: Path, manifest: dict) -> tuple[HeaderContract | None, list[str]]:
    try:
        raw = path.read_text()
    except OSError as exc:
        return None, [f"_headers: cannot read {path}: {exc}"]
    return validate_headers(raw, manifest)


def response_header(headers: dict[str, str], name: str) -> str:
    values = [value for key, value in headers.items() if key.lower() == name.lower()]
    return ", ".join(values)


def validate_live_direct_headers(
    errors: list[str],
    label: str,
    headers: dict[str, str],
    contract: HeaderContract,
    *,
    exclude: frozenset[str] = frozenset(),
) -> None:
    for name, expected in contract.direct_response.items():
        if name in exclude:
            continue
        actual = response_header(headers, name)
        if actual != expected:
            errors.append(
                f"{label} {name} header must be exactly {expected!r}; found {actual!r}"
            )


def validate_speculation_content_type(
    errors: list[str], label: str, headers: dict[str, str], contract: HeaderContract
) -> None:
    raw = response_header(headers, "content-type")
    media_type = raw.split(";", 1)[0].strip().lower()
    if "," in raw or media_type != contract.speculation_content_type:
        errors.append(
            f"{label} Content-Type must be {contract.speculation_content_type!r}; found {raw!r}"
        )
