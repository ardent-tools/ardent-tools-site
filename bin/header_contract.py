#!/usr/bin/env python3
"""Exact Cloudflare Pages header contract for retained and live output."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple


ROOT_PATH = "/*"
SPECULATION_PATH = "/speculation-rules.json"
SPECULATION_MEDIA_TYPE = "application/speculationrules+json"

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


def manifest_request_url(manifest: dict, output_path: str) -> str | None:
    matches = [
        item.get("request_url")
        for item in manifest.get("resources", [])
        if isinstance(item, dict) and item.get("output_path") == output_path
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
    return HeaderContract(direct, SPECULATION_MEDIA_TYPE), []


def parse_headers(raw: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    sections: dict[str, dict[str, str]] = {}
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
            continue

        if current_path is None:
            errors.append(f"_headers:{line_number}: header has no valid path declaration")
            continue
        if stripped.startswith("!"):
            errors.append(
                f"_headers:{line_number}: detach operations are unsupported by this exact contract"
            )
            continue
        if ":" not in stripped:
            errors.append(f"_headers:{line_number}: malformed header declaration {stripped!r}")
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
    return sections, errors


def validate_headers(raw: str, manifest: dict) -> tuple[HeaderContract | None, list[str]]:
    contract, errors = expected_contract(manifest)
    sections, parse_errors = parse_headers(raw)
    errors.extend(parse_errors)
    if contract is None:
        return None, errors
    expected_sections = {
        ROOT_PATH: contract.direct_response,
        SPECULATION_PATH: {"content-type": contract.speculation_content_type},
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
