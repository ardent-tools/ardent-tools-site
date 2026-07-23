#!/usr/bin/env python3
"""Deterministic retained-artifact authority for every served HTML body."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlparse


AUTHORITY_NAME = "release-html.json"
SCHEMA_VERSION = 1
MAX_ROUTES = 256
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
ROUTE_RE = re.compile(r"^/[A-Za-z0-9._~/-]*/$")
HTML_OUTPUT_RE = re.compile(r"^[A-Za-z0-9._~/-]+\.html$")
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def origin(url: str) -> tuple[str, str | None, int | None]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return scheme, parsed.hostname, parsed.port or default_port


def route_output_path(request_path: str) -> str:
    if request_path == "/":
        return "index.html"
    if (
        not ROUTE_RE.fullmatch(request_path)
        or "//" in request_path
        or "\\" in request_path
    ):
        raise ValueError(f"noncanonical HTML request path {request_path!r}")
    if "%" in request_path:
        raise ValueError(f"encoded HTML request path is not allowed: {request_path!r}")
    if any(part in {".", ".."} for part in request_path.strip("/").split("/")):
        raise ValueError(f"dot segment in HTML request path {request_path!r}")
    return f"{request_path.strip('/')}/index.html"


def validate_base_url(base_url: str) -> str:
    try:
        parsed = urlparse(base_url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"malformed HTML authority base URL: {exc}") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or base_url != f"https://{parsed.hostname}"
    ):
        raise ValueError(
            "HTML authority base URL must be one lowercase HTTPS origin without "
            "credentials, port, path, query, fragment, or trailing slash"
        )
    return base_url + "/"


def html_request_path(output_path: str) -> str:
    if (
        not HTML_OUTPUT_RE.fullmatch(output_path)
        or output_path.startswith(("/", "."))
        or "//" in output_path
        or "\\" in output_path
        or "%" in output_path
    ):
        raise ValueError(f"noncanonical retained HTML output path {output_path!r}")
    parts = PurePosixPath(output_path).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"noncanonical retained HTML output path {output_path!r}")
    if output_path == "index.html":
        return "/"
    if output_path.endswith("/index.html"):
        return f"/{output_path[:-len('index.html')]}"
    return f"/{output_path}"


def sitemap_paths(output: Path, base_url: str) -> list[str]:
    sitemap_path = output / "sitemap.xml"
    try:
        root = ET.fromstring(sitemap_path.read_bytes())
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"cannot parse retained sitemap.xml: {exc}") from exc
    if root.tag != f"{SITEMAP}urlset":
        raise ValueError(f"sitemap.xml root must be urlset, found {root.tag!r}")
    urls = [node.text or "" for node in root.findall(f"{SITEMAP}url/{SITEMAP}loc")]
    if not 1 <= len(urls) <= MAX_ROUTES:
        raise ValueError(f"sitemap route count {len(urls)} is outside 1..{MAX_ROUTES}")
    root_url = validate_base_url(base_url)
    paths: list[str] = []
    seen: set[str] = set()
    for url in urls:
        try:
            parsed = urlparse(url)
            url_origin = origin(url)
        except ValueError as exc:
            raise ValueError(f"malformed sitemap URL {url!r}: {exc}") from exc
        if url_origin != origin(root_url):
            raise ValueError(f"sitemap URL is not same-origin: {url!r}")
        if parsed.query or parsed.fragment:
            raise ValueError(f"sitemap HTML URL has query or fragment: {url!r}")
        request_path = parsed.path
        route_output_path(request_path)
        exact_url = urljoin(root_url, request_path.lstrip("/"))
        if url != exact_url:
            raise ValueError(f"sitemap URL is not canonical: {url!r}, expected {exact_url!r}")
        if request_path in seen:
            raise ValueError(f"sitemap repeats HTML route {request_path!r}")
        seen.add(request_path)
        paths.append(request_path)
    return paths


def regular_file(root: Path, relative: str) -> Path:
    path = root / relative
    cursor = root
    for part in PurePosixPath(relative).parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"retained HTML authority path traverses a symlink: {relative}")
    if not path.is_file():
        raise ValueError(f"retained HTML authority path is not a regular file: {relative}")
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"retained HTML authority path escapes root: {relative}") from exc
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_authority(output: Path, revision: str, base_url: str) -> dict:
    if not REVISION_RE.fullmatch(revision):
        raise ValueError("HTML authority revision must be exactly one lowercase 40-hex value")
    output = output.resolve()
    canonical_paths = set(sitemap_paths(output, base_url))
    for path in output.rglob("*"):
        if path.is_symlink():
            raise ValueError(
                "retained HTML authority tree contains a symlink: "
                f"{path.relative_to(output)}"
            )
    html_paths = sorted(
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
        and path.suffix.lower() == ".html"
        if path.relative_to(output).as_posix() != "404.html"
    )
    if not 1 <= len(html_paths) <= MAX_ROUTES:
        raise ValueError(
            f"retained HTML route count {len(html_paths)} is outside 1..{MAX_ROUTES}"
        )
    routes = []
    seen_requests: set[str] = set()
    for relative in html_paths:
        request_path = html_request_path(relative)
        if request_path in seen_requests:
            raise ValueError(f"retained HTML routes collide at {request_path!r}")
        seen_requests.add(request_path)
        routes.append(
            {
                "request_path": request_path,
                "output_path": relative,
                "sha256": digest(regular_file(output, relative)),
                "in_sitemap": request_path in canonical_paths,
            }
        )
    missing_canonical = canonical_paths - seen_requests
    if missing_canonical:
        raise ValueError(
            f"sitemap routes lack retained HTML files: {sorted(missing_canonical)!r}"
        )

    top_level_404 = regular_file(output, "404.html")
    routed_404 = regular_file(output, "404/index.html")
    if top_level_404.read_bytes() != routed_404.read_bytes():
        raise ValueError("404.html and 404/index.html must be byte-identical")
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": revision,
        "route_count": len(routes),
        "routes": routes,
        "custom_404": {
            "output_path": "404.html",
            "sha256": digest(top_level_404),
        },
    }


def serialize_authority(authority: dict) -> bytes:
    return (json.dumps(authority, indent=2, sort_keys=True) + "\n").encode("utf-8")


def strict_json_loads(raw: bytes) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-JSON constant {value!r}")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        document: dict[str, object] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"duplicate key {key!r}")
            document[key] = value
        return document

    text = raw.decode("utf-8", errors="strict")
    return json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )


def validate_authority(
    raw: bytes, *, output: Path, expected_revision: str, base_url: str
) -> tuple[dict, list[str]]:
    try:
        document = strict_json_loads(raw)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        return {}, [f"{AUTHORITY_NAME} is not strict UTF-8 JSON: {exc}"]
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "revision",
        "route_count",
        "routes",
        "custom_404",
    }:
        return document if isinstance(document, dict) else {}, [
            f"{AUTHORITY_NAME} has unexpected or missing top-level keys"
        ]
    try:
        expected = build_authority(output, expected_revision, base_url)
    except (OSError, ValueError) as exc:
        return document, [f"cannot derive retained HTML authority: {exc}"]
    errors: list[str] = []
    if document != expected:
        errors.append(f"{AUTHORITY_NAME} differs from the exact retained HTML tree")
    return document, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    try:
        authority = build_authority(args.output, args.revision, args.base_url)
        destination = args.output / AUTHORITY_NAME
        destination.write_bytes(serialize_authority(authority))
        _, errors = validate_authority(
            destination.read_bytes(),
            output=args.output,
            expected_revision=args.revision,
            base_url=args.base_url,
        )
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"ERROR: cannot generate HTML authority: {exc}\n")
        return 1
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    sys.stdout.write(
        f"PASS: HTML authority covers {authority['route_count']} retained routes and custom 404\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
