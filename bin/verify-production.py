#!/usr/bin/env python3
"""Verify the authored/runtime boundary after a production deployment."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
import tomllib
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
ASSET_HASH_RE = re.compile(r"^[0-9a-f]{20}$")
ASSET_EPOCH_RE = re.compile(r"^[1-9][0-9]*$")
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
MAX_SITEMAP_HTML_ROUTES = 256
STRUCTURED_RESOURCE_PATHS = (
    "/atom.xml",
    "/systems.json",
    "/site.webmanifest",
    "/speculation-rules.json",
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and "src" in attributes:
            self.references.append(("JavaScript", attributes.get("src") or ""))
        if tag == "link" and "stylesheet" in (attributes.get("rel") or "").lower().split():
            self.references.append(("CSS", attributes.get("href") or ""))


def merge_headers(items: list[tuple[str, str]]) -> dict[str, str]:
    """Preserve repeated response fields as their effective comma-joined value."""
    merged: dict[str, str] = {}
    for name, value in items:
        key = name.lower()
        merged[key] = f"{merged[key]}, {value}" if key in merged else value
    return merged


def request(url: str, timeout: float, follow: bool = True) -> tuple[int, dict[str, str], bytes]:
    opener = build_opener() if follow else build_opener(NoRedirect())
    req = Request(url, headers={"User-Agent": "ardent-tools-production-verifier/1"})
    try:
        with opener.open(req, timeout=timeout) as response:
            return response.status, merge_headers(list(response.headers.items())), response.read()
    except HTTPError as exc:
        return exc.code, merge_headers(list(exc.headers.items())), exc.read()


def header(headers: dict[str, str], name: str) -> str:
    return ", ".join(
        value for key, value in headers.items() if key.lower() == name.lower()
    )


def cache_directives(headers: dict[str, str]) -> list[tuple[str, str | None]]:
    directives: list[tuple[str, str | None]] = []
    for raw_directive in header(headers, "Cache-Control").split(","):
        raw_directive = raw_directive.strip()
        if not raw_directive:
            continue
        name, separator, value = raw_directive.partition("=")
        directives.append(
            (
                name.strip().lower(),
                value.strip().strip('"').lower() if separator else None,
            )
        )
    return directives


def validate_no_store_cache(
    errors: list[str], label: str, headers: dict[str, str]
) -> None:
    cache_control = header(headers, "Cache-Control")
    directives = cache_directives(headers)
    expected = Counter({("no-store", None): 1, ("no-transform", None): 1})
    if Counter(directives) != expected:
        errors.append(
            f"{label} Cache-Control must be exactly no-store, no-transform; "
            f"found {cache_control!r}"
        )


def same_origin(left: str, right: str) -> bool:
    def origin(url: str) -> tuple[str, str | None, int | None]:
        parsed = urlparse(url)
        default_port = 443 if parsed.scheme.lower() == "https" else 80
        return parsed.scheme.lower(), parsed.hostname, parsed.port or default_port

    try:
        return origin(left) == origin(right)
    except ValueError:
        return False


def asset_identity(url: str) -> tuple[str, str, str, tuple[tuple[str, str], ...]]:
    parsed = urlparse(url)
    other_query = tuple(
        (name, value)
        for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        if name not in {"h", "v"}
    )
    return parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, other_query


def collect_hashed_assets(
    errors: list[str], base_url: str, page_url: str, body: str, asset_epoch: str
) -> list[tuple[str, str, str]]:
    parser = AssetParser()
    parser.feed(body)
    assets: list[tuple[str, str, str]] = []
    kinds = {kind for kind, _ in parser.references}
    for required_kind in ("CSS", "JavaScript"):
        if required_kind not in kinds:
            errors.append(f"{page_url}: no authored {required_kind} asset reference found")
    for kind, reference in parser.references:
        try:
            resolved = urljoin(page_url, reference)
        except ValueError:
            errors.append(f"{page_url}: malformed {kind} asset URL: {reference!r}")
            continue
        if not same_origin(base_url, resolved):
            errors.append(f"{page_url}: external {kind} asset is not allowed: {reference!r}")
            continue
        parsed = urlparse(resolved)
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        names = [name for name, _ in pairs]
        if len(pairs) != 2 or Counter(names) != Counter({"h": 1, "v": 1}):
            errors.append(
                f"{page_url}: {kind} asset must carry exactly one h and one v query and "
                f"no others: {reference!r}"
            )
            continue
        values = dict(pairs)
        if not ASSET_HASH_RE.fullmatch(values["h"]):
            errors.append(
                f"{page_url}: {kind} asset has malformed h query value {values['h']!r}: "
                f"{reference!r}"
            )
            continue
        if values["v"] != asset_epoch:
            errors.append(
                f"{page_url}: {kind} asset has v={values['v']!r}, expected "
                f"{asset_epoch!r}: {reference!r}"
            )
            continue
        assets.append((resolved, values["h"], kind))
    return assets


def sitemap_html_paths(
    errors: list[str], site_root: str, body: bytes
) -> list[str]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        errors.append(f"/sitemap.xml strict XML parse failed: {exc}")
        return []
    urls = [node.text or "" for node in root.findall(f"{SITEMAP}url/{SITEMAP}loc")]
    if not urls:
        errors.append("/sitemap.xml contains no authored HTML routes")
        return []
    if len(urls) > MAX_SITEMAP_HTML_ROUTES:
        errors.append(
            f"/sitemap.xml contains {len(urls)} routes, exceeding bounded verifier limit "
            f"{MAX_SITEMAP_HTML_ROUTES}"
        )
        return []
    paths: list[str] = []
    seen: set[str] = set()
    for url in urls:
        try:
            parsed = urlparse(url)
        except ValueError:
            errors.append(f"/sitemap.xml has malformed route: {url!r}")
            continue
        if not same_origin(site_root, url):
            errors.append(f"/sitemap.xml has external route: {url!r}")
            continue
        if parsed.query or parsed.fragment or not parsed.path.endswith("/"):
            errors.append(f"/sitemap.xml has non-HTML route shape: {url!r}")
            continue
        if parsed.path in seen:
            errors.append(f"/sitemap.xml repeats route: {parsed.path}")
            continue
        seen.add(parsed.path)
        paths.append(parsed.path)
    for required in ("/", "/evidence/"):
        if required not in seen:
            errors.append(f"/sitemap.xml lacks required route {required}")
    return paths


def distinct_assets(
    errors: list[str], references: list[tuple[str, str, str]]
) -> dict[str, tuple[str, str]]:
    assets: dict[str, tuple[str, str]] = {}
    identities: dict[tuple[str, str, str, tuple[tuple[str, str], ...]], tuple[str, str]] = {}
    for asset_url, authored_hash, kind in references:
        identity = asset_identity(asset_url)
        prior = identities.get(identity)
        if prior and prior[0] != authored_hash:
            errors.append(
                f"conflicting authored hashes for {identity[2]}: {prior[0]} at {prior[1]!r}, "
                f"{authored_hash} at {asset_url!r}"
            )
        else:
            identities[identity] = (authored_hash, asset_url)
        prior_asset = assets.get(asset_url)
        if prior_asset and prior_asset != (authored_hash, kind):
            errors.append(f"conflicting duplicate authored asset reference: {asset_url!r}")
        else:
            assets[asset_url] = (authored_hash, kind)
    return assets


def verify(
    base_url: str, timeout: float, expected_revision: str, asset_epoch: str
) -> list[str]:
    errors: list[str] = []
    site_root = base_url.rstrip("/") + "/"
    revision_url = urljoin(site_root, "build-revision.txt")
    revision_status, revision_headers, revision_body = request(revision_url, timeout)
    if revision_status != 200:
        errors.append(f"/build-revision.txt returned {revision_status}, expected 200")
    expected_body = f"{expected_revision}\n".encode()
    if revision_body != expected_body:
        errors.append(
            "deployed revision mismatch: "
            f"expected {expected_revision!r}, got {revision_body.decode('utf-8', errors='replace').strip()!r}"
        )
    validate_no_store_cache(errors, "/build-revision.txt", revision_headers)

    sitemap_url = urljoin(site_root, "sitemap.xml")
    sitemap_status, sitemap_headers, sitemap_body = request(sitemap_url, timeout)
    if sitemap_status != 200:
        errors.append(f"/sitemap.xml returned {sitemap_status}, expected 200")
    validate_no_store_cache(errors, "/sitemap.xml", sitemap_headers)
    html_paths = sitemap_html_paths(errors, site_root, sitemap_body)

    for path in STRUCTURED_RESOURCE_PATHS:
        resource_url = urljoin(site_root, path.lstrip("/"))
        status, resource_headers, _ = request(resource_url, timeout, follow=False)
        if status != 200:
            errors.append(f"{path} returned {status}, expected 200")
        validate_no_store_cache(errors, path, resource_headers)

    pages: dict[str, str] = {}
    asset_references: list[tuple[str, str, str]] = []
    for path in html_paths:
        page_url = urljoin(site_root, path.lstrip("/"))
        status, headers, body_bytes = request(page_url, timeout)
        body = body_bytes.decode("utf-8", errors="replace")
        if status != 200:
            errors.append(f"{path} returned {status}, expected 200")
        validate_no_store_cache(errors, path, headers)

        csp = header(headers, "Content-Security-Policy")
        if "script-src 'self'" not in csp or "'unsafe-inline'" in csp or "wasm-unsafe-eval" in csp:
            errors.append(f"{path} strict zero-cast CSP is absent: {csp!r}")
        if "/cdn-cgi/" in body or "__cf_email__" in body or "data-cfemail" in body:
            errors.append(f"{path} has Cloudflare email-protection markup/script injected")

        asset_references.extend(
            collect_hashed_assets(errors, site_root, page_url, body, asset_epoch)
        )
        pages[path] = body

    evidence_url = urljoin(site_root, "evidence/")
    evidence_body = pages.get("/evidence/", "")
    for marker in (
        'href="https://ardent.tools/evidence/"',
        "Evidence register",
        "0 published casts.",
    ):
        if marker not in evidence_body:
            errors.append(f"/evidence/ lacks deployment marker {marker!r}")

    assets = distinct_assets(errors, asset_references)

    for asset_url, (authored_hash, kind) in assets.items():
        asset_status, asset_headers, asset_body = request(asset_url, timeout, follow=False)
        if asset_status != 200:
            errors.append(f"authored {kind} asset {asset_url!r} returned {asset_status}, expected 200")
            continue
        validate_no_store_cache(
            errors, f"authored {kind} asset {asset_url!r}", asset_headers
        )
        digest = hashlib.sha256(asset_body).hexdigest()
        if not digest.startswith(authored_hash):
            errors.append(
                f"authored {kind} asset digest mismatch for {asset_url!r}: "
                f"h={authored_hash}, SHA-256={digest}"
            )

    demos_url = urljoin(site_root, "demos/")
    redirect_status, redirect_headers, _ = request(demos_url, timeout, follow=False)
    location = header(redirect_headers, "Location")
    if redirect_status not in (301, 308):
        errors.append(f"/demos/ returned {redirect_status}, expected permanent redirect")
    if urljoin(demos_url, location) != evidence_url:
        errors.append(f"/demos/ redirects to {location!r}, expected /evidence/")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://ardent.tools")
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--expected-revision", required=True)
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")
    if not REVISION_RE.fullmatch(args.expected_revision):
        parser.error("--expected-revision must be exactly one lowercase 40-hex revision")
    try:
        config = tomllib.loads(Path("config.toml").read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        parser.error(f"cannot read asset epoch from config.toml: {exc}")
    asset_epoch = config.get("extra", {}).get("asset_epoch")
    if not isinstance(asset_epoch, str) or not ASSET_EPOCH_RE.fullmatch(asset_epoch):
        parser.error("config.toml extra.asset_epoch must be a nonzero decimal string")

    last_errors: list[str] = []
    for attempt in range(1, args.attempts + 1):
        try:
            last_errors = verify(
                args.base_url, args.timeout, args.expected_revision, asset_epoch
            )
        except (OSError, URLError) as exc:
            last_errors = [f"request failed: {exc}"]
        if not last_errors:
            sys.stdout.write(f"PASS: production boundary verified on attempt {attempt}\n")
            return 0
        if attempt < args.attempts:
            sys.stderr.write(
                f"attempt {attempt}/{args.attempts} not current: {'; '.join(last_errors)}\n"
            )
            time.sleep(args.delay)

    for error in last_errors:
        sys.stderr.write(f"ERROR: {error}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
