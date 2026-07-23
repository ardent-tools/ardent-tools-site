#!/usr/bin/env python3
"""Derive Cloudflare Pages Function routing and its release identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import tomllib
from pathlib import Path

from header_contract import ROOT_PATH, parse_headers
from redirect_contract import load_redirects


ROOT = Path(__file__).resolve().parents[1]
FUNCTION_RELATIVE_PATH = "functions/[[path]].js"
FUNCTION_SOURCE = ROOT / FUNCTION_RELATIVE_PATH
WRANGLER_RELATIVE_PATH = "wrangler.toml"
WRANGLER_SOURCE = ROOT / WRANGLER_RELATIVE_PATH
ROUTES_NAME = "_routes.json"
BOUNDARY_NAME = "runtime-boundary.json"
AUTHORITY_NAME = "release-html.json"
MANIFEST_NAME = "release-resources.json"
ROUTES_SCHEMA_VERSION = 1
BOUNDARY_SCHEMA_VERSION = 2
MAX_ROUTE_RULES = 100
MAX_ROUTE_LENGTH = 100
SAFE_ROUTE_RE = re.compile(r"^/[A-Za-z0-9._~!$&'()+,;=:@%*/-]*$")
ADDRESSED_RESOURCE_RE = re.compile(r"^a/[0-9a-f]{64}\.[A-Za-z0-9]+$")
CONTROL_FILES = frozenset({"_headers", "_redirects", ROUTES_NAME})
DIRECT_HEADERS_JSON_START = "/* DIRECT_RESPONSE_HEADERS_JSON_START */"
DIRECT_HEADERS_JSON_END = "/* DIRECT_RESPONSE_HEADERS_JSON_END */"
EXPECTED_WRANGLER_CONFIG = {
    "name": "ardent-tools",
    "pages_build_output_dir": "./public",
    "compatibility_date": "2026-07-21",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path, label: str) -> tuple[dict, list[str]]:
    try:
        value = json.loads(path.read_text())
    except OSError as exc:
        return {}, [f"{label}: cannot read {path}: {exc}"]
    except json.JSONDecodeError as exc:
        return {}, [f"{label}: invalid JSON: {exc}"]
    if not isinstance(value, dict):
        return {}, [f"{label}: root must be an object"]
    return value, []


def validate_route(route: object, label: str) -> list[str]:
    errors: list[str] = []
    if (
        not isinstance(route, str)
        or not SAFE_ROUTE_RE.fullmatch(route)
        or route.startswith("//")
        or "\\" in route
        or "?" in route
        or "#" in route
    ):
        errors.append(f"{label}: invalid Pages route {route!r}")
    elif len(route) > MAX_ROUTE_LENGTH:
        errors.append(
            f"{label}: route exceeds Cloudflare's {MAX_ROUTE_LENGTH}-character limit: {route!r}"
        )
    return errors


def artifact_resource_paths(output: Path) -> tuple[set[str], list[str]]:
    """Return exact non-HTML request paths which must stay on static serving."""
    paths = {f"/{MANIFEST_NAME}", f"/{BOUNDARY_NAME}", "/a/*"}
    errors: list[str] = []
    for path in sorted(output.rglob("*")):
        try:
            metadata = path.lstat()
        except OSError as exc:
            errors.append(f"pages runtime: cannot inspect {path}: {exc}")
            continue
        if stat.S_ISLNK(metadata.st_mode):
            errors.append(
                f"pages runtime: retained artifact must not contain a symlink: {path.relative_to(output)}"
            )
            continue
        if not stat.S_ISREG(metadata.st_mode):
            continue
        relative = path.relative_to(output).as_posix()
        # Canonical HTML routes are supplied by release-html.json below.
        # Physical index.html aliases may safely cross the Function: Pages
        # resolves them as redirects, and the Function preserves that status
        # and Location while attaching the direct-response header contract.
        if relative in CONTROL_FILES or relative.endswith(".html"):
            continue
        if relative.startswith("a/") and not ADDRESSED_RESOURCE_RE.fullmatch(relative):
            errors.append(
                "pages runtime: physical resource path must carry one full SHA-256 "
                f"and extension: {relative}"
            )
        if not relative.startswith("a/"):
            paths.add(f"/{relative}")
    return paths, errors


def validate_overlapping_rules(routes: list[str], label: str) -> list[str]:
    """Mirror Wrangler's rejection of rules hidden by an ending splat."""
    errors: list[str] = []
    ending_splats = [route for route in routes if route.endswith("/*")]
    for splat in ending_splats:
        prefix = splat[:-1]
        for route in routes:
            if route != splat and route.startswith(prefix):
                errors.append(
                    f"{ROUTES_NAME}: overlapping {label} rules {splat!r} and {route!r}"
                )
    return errors


def authority_paths(output: Path) -> tuple[set[str], list[str]]:
    authority, errors = read_json(output / AUTHORITY_NAME, AUTHORITY_NAME)
    if errors:
        return set(), errors
    routes = authority.get("routes")
    if not isinstance(routes, list):
        return set(), [f"{AUTHORITY_NAME}: routes must be an array"]
    result: set[str] = set()
    for index, item in enumerate(routes):
        if not isinstance(item, dict) or not isinstance(item.get("request_path"), str):
            errors.append(
                f"{AUTHORITY_NAME}: routes[{index}].request_path must be a string"
            )
            continue
        result.add(item["request_path"])
    return result, errors


def build_routes(output: Path) -> tuple[dict, list[str]]:
    errors: list[str] = []
    resources, resource_errors = artifact_resource_paths(output)
    pages, authority_errors = authority_paths(output)
    redirects, redirect_errors = load_redirects(output / "_redirects")
    errors.extend(resource_errors)
    errors.extend(authority_errors)
    errors.extend(redirect_errors)

    excludes = sorted(resources | pages | {rule.source for rule in redirects})
    for index, route in enumerate(excludes):
        errors.extend(validate_route(route, f"{ROUTES_NAME}: exclude[{index}]"))
    errors.extend(validate_overlapping_rules(["/*"], "include"))
    errors.extend(validate_overlapping_rules(excludes, "exclude"))
    if "/*" in excludes:
        errors.append(
            f"{ROUTES_NAME}: exclude rules must not disable the catch-all Function"
        )
    if len(excludes) + 1 > MAX_ROUTE_RULES:
        errors.append(
            f"{ROUTES_NAME}: {len(excludes) + 1} include/exclude rules exceed Cloudflare's {MAX_ROUTE_RULES}-rule limit"
        )
    return {
        "version": ROUTES_SCHEMA_VERSION,
        "include": ["/*"],
        "exclude": excludes,
    }, errors


def serialize(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def function_bytes() -> tuple[bytes, list[str]]:
    try:
        metadata = FUNCTION_SOURCE.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return b"", [
                f"pages runtime: {FUNCTION_RELATIVE_PATH} must be one regular non-symlink file"
            ]
        return FUNCTION_SOURCE.read_bytes(), []
    except OSError as exc:
        return b"", [f"pages runtime: cannot read {FUNCTION_RELATIVE_PATH}: {exc}"]


def wrangler_bytes() -> tuple[bytes, list[str]]:
    try:
        metadata = WRANGLER_SOURCE.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return b"", [
                f"pages runtime: {WRANGLER_RELATIVE_PATH} must be one regular non-symlink file"
            ]
        return WRANGLER_SOURCE.read_bytes(), []
    except OSError as exc:
        return b"", [f"pages runtime: cannot read {WRANGLER_RELATIVE_PATH}: {exc}"]


def validate_wrangler_config(source: bytes) -> list[str]:
    try:
        value = tomllib.loads(source.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return [
            f"pages runtime: {WRANGLER_RELATIVE_PATH} is not strict UTF-8 TOML: {exc}"
        ]
    if value != EXPECTED_WRANGLER_CONFIG:
        return [
            f"pages runtime: {WRANGLER_RELATIVE_PATH} must be the exact production Pages config"
        ]
    return []


def function_direct_headers(source: bytes) -> tuple[dict[str, str], list[str]]:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {}, [f"pages runtime: Function source must be UTF-8: {exc}"]
    if (
        text.count(DIRECT_HEADERS_JSON_START) != 1
        or text.count(DIRECT_HEADERS_JSON_END) != 1
    ):
        return {}, [
            "pages runtime: Function must contain exactly one delimited direct-header contract"
        ]
    raw = text.split(DIRECT_HEADERS_JSON_START, 1)[1].split(DIRECT_HEADERS_JSON_END, 1)[
        0
    ]
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, [
            f"pages runtime: Function direct-header contract is invalid JSON: {exc}"
        ]
    if not isinstance(value, dict) or any(
        not isinstance(name, str)
        or name != name.lower()
        or not isinstance(header_value, str)
        or not header_value
        for name, header_value in value.items()
    ):
        return {}, [
            "pages runtime: Function direct-header contract must be a lowercase string map"
        ]
    return value, []


def validate_function_headers(output: Path) -> list[str]:
    source, errors = function_bytes()
    function_headers, function_errors = function_direct_headers(source)
    errors.extend(function_errors)
    try:
        raw_headers = (output / "_headers").read_text()
    except OSError as exc:
        return errors + [f"pages runtime: cannot read retained _headers: {exc}"]
    sections, header_errors = parse_headers(raw_headers)
    errors.extend(header_errors)
    static_headers = sections.get(ROOT_PATH)
    if static_headers is None:
        errors.append(f"pages runtime: retained _headers lacks {ROOT_PATH!r}")
    elif function_headers != {
        name: value
        for name, value in static_headers.items()
        if name != "speculation-rules"
    }:
        errors.append(
            "pages runtime: Function static direct headers differ from retained /* contract"
        )
    return errors


def build_boundary(routes_bytes: bytes) -> tuple[dict, list[str]]:
    source, errors = function_bytes()
    wrangler, wrangler_errors = wrangler_bytes()
    errors.extend(wrangler_errors)
    if not wrangler_errors:
        errors.extend(validate_wrangler_config(wrangler))
    return {
        "schema_version": BOUNDARY_SCHEMA_VERSION,
        "function": {
            "path": FUNCTION_RELATIVE_PATH,
            "sha256": sha256_bytes(source),
        },
        "routes": {
            "path": ROUTES_NAME,
            "sha256": sha256_bytes(routes_bytes),
        },
        "wrangler": {
            "path": WRANGLER_RELATIVE_PATH,
            "sha256": sha256_bytes(wrangler),
        },
    }, errors


def expected_runtime(output: Path) -> tuple[bytes, bytes, list[str]]:
    routes, errors = build_routes(output)
    routes_bytes = serialize(routes)
    boundary, boundary_errors = build_boundary(routes_bytes)
    errors.extend(boundary_errors)
    errors.extend(validate_function_headers(output))
    return routes_bytes, serialize(boundary), errors


def validate_runtime(output: Path) -> list[str]:
    expected_routes, expected_boundary, errors = expected_runtime(output)
    for name, expected in (
        (ROUTES_NAME, expected_routes),
        (BOUNDARY_NAME, expected_boundary),
    ):
        path = output / name
        try:
            actual = path.read_bytes()
        except OSError as exc:
            errors.append(f"pages runtime: cannot read retained {name}: {exc}")
            continue
        if actual != expected:
            errors.append(
                f"pages runtime: retained {name} differs from derived authority"
            )
    return errors


def write_runtime(output: Path) -> tuple[int, int]:
    routes_bytes, boundary_bytes, errors = expected_runtime(output)
    if errors:
        raise ValueError("\n".join(errors))
    (output / ROUTES_NAME).write_bytes(routes_bytes)
    (output / BOUNDARY_NAME).write_bytes(boundary_bytes)
    routes = json.loads(routes_bytes)
    return len(routes["include"]), len(routes["exclude"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, help="retained Zola output directory")
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        include_count, exclude_count = write_runtime(output)
    except ValueError as exc:
        for error in str(exc).splitlines():
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    sys.stdout.write(
        "PASS: Pages runtime routes keep "
        f"{exclude_count} retained/redirect paths static and "
        f"{include_count} catch-all active\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
