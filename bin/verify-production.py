#!/usr/bin/env python3
"""Verify the authored/runtime boundary after a production deployment."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from header_contract import (
    HeaderContract,
    load_headers,
    validate_live_direct_headers,
    validate_speculation_content_type,
)
from html_authority import AUTHORITY_NAME, validate_authority, validate_base_url
from pages_runtime import BOUNDARY_NAME, validate_runtime
from release_manifest import BASE_URL, read_contract, validate_manifest
from redirect_contract import RedirectRule, load_redirects, redirect_probe_path

REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
ADDRESSED_ASSET_RE = re.compile(r"^/a/([0-9a-f]{64})(\.[A-Za-z0-9]+)$")
CF_RAY_RE = re.compile(r"^[0-9a-f]{16}-([A-Z]{3})$")
CANONICAL_ORIGIN = BASE_URL.rstrip("/")
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
MAX_SITEMAP_HTML_ROUTES = 256
REQUIRED_RELEASE_LOGICAL_PATHS = (
    "atom.xml",
    "build-revision.txt",
    "career-claims.json",
    "llms.txt",
    AUTHORITY_NAME,
    BOUNDARY_NAME,
    "robots.txt",
    "sitemap.xml",
    "systems.json",
    "site.webmanifest",
    "speculation-rules.json",
)
CUSTOM_404_MARKERS = ("404: no such path", "Return home")
STRICT_ZERO_CAST_CSP = {
    "default-src": ("'self'",),
    "img-src": ("'self'",),
    "style-src": ("'self'",),
    "script-src": ("'self'",),
    "font-src": ("'self'",),
    "connect-src": ("'self'",),
    "form-action": ("'self'",),
    "base-uri": ("'self'",),
    "frame-ancestors": ("'none'",),
    "object-src": ("'none'",),
    "manifest-src": ("'self'",),
    "worker-src": ("'none'",),
    "upgrade-insecure-requests": (),
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[tuple[str, str]] = []
        self.canonicals: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and "src" in attributes:
            self.references.append(("JavaScript", attributes.get("src") or ""))
        if (
            tag == "link"
            and "stylesheet" in (attributes.get("rel") or "").lower().split()
        ):
            self.references.append(("CSS", attributes.get("href") or ""))
        if (
            tag == "link"
            and "canonical" in (attributes.get("rel") or "").lower().split()
        ):
            self.canonicals.append(attributes.get("href") or "")


def merge_headers(items: list[tuple[str, str]]) -> dict[str, str]:
    """Preserve repeated response fields as their effective comma-joined value."""
    merged: dict[str, str] = {}
    for name, value in items:
        key = name.lower()
        merged[key] = f"{merged[key]}, {value}" if key in merged else value
    return merged


def request(
    url: str, timeout: float, follow: bool = True
) -> tuple[int, dict[str, str], bytes]:
    opener = build_opener() if follow else build_opener(NoRedirect())
    req = Request(url, headers={"User-Agent": "ardent-tools-production-verifier/1"})
    try:
        with opener.open(req, timeout=timeout) as response:
            return (
                response.status,
                merge_headers(list(response.headers.items())),
                response.read(),
            )
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


def validate_strict_csp(errors: list[str], label: str, headers: dict[str, str]) -> None:
    raw = header(headers, "Content-Security-Policy")
    parsed: dict[str, tuple[str, ...]] = {}
    duplicates: list[str] = []
    for segment in raw.split(";"):
        tokens = segment.strip().split()
        if not tokens:
            continue
        name = tokens[0].lower()
        if name in parsed:
            duplicates.append(name)
        parsed[name] = tuple(tokens[1:])
    if duplicates or parsed != STRICT_ZERO_CAST_CSP:
        errors.append(f"{label} strict zero-cast CSP differs: {raw!r}")


def validate_html_content_type(
    errors: list[str], label: str, headers: dict[str, str]
) -> None:
    raw = header(headers, "Content-Type")
    media_type = raw.split(";", 1)[0].strip().lower()
    if "," in raw or media_type != "text/html":
        errors.append(f"{label} Content-Type must be HTML; found {raw!r}")


def validate_html_boundary(
    errors: list[str],
    label: str,
    headers: dict[str, str],
    body: str,
    header_contract: HeaderContract,
) -> None:
    validate_no_store_cache(errors, label, headers)
    validate_strict_csp(errors, label, headers)
    validate_live_direct_headers(
        errors,
        label,
        headers,
        header_contract,
        exclude=frozenset({"cache-control", "content-security-policy"}),
    )
    if "/cdn-cgi/" in body or "__cf_email__" in body or "data-cfemail" in body:
        errors.append(f"{label} has Cloudflare email-protection markup/script injected")


def validate_canonical(
    errors: list[str], page_url: str, expected_url: str, body: str
) -> None:
    parser = AssetParser()
    parser.feed(body)
    if len(parser.canonicals) != 1:
        errors.append(
            f"{page_url}: expected exactly one canonical link, found {len(parser.canonicals)}"
        )
        return
    try:
        canonical = urljoin(page_url, parser.canonicals[0])
    except ValueError:
        errors.append(f"{page_url}: malformed canonical link {parser.canonicals[0]!r}")
        return
    if canonical != expected_url:
        errors.append(
            f"{page_url}: canonical resolves to {canonical!r}, expected {expected_url!r}"
        )


def missing_probe_path(expected_revision: str) -> str:
    material = f"ardent-tools custom 404 probe\0{expected_revision}".encode("ascii")
    token = hashlib.sha256(material).hexdigest()[:24]
    return f"/__ardent-missing-{token}/"


def missing_probe_is_disjoint(
    errors: list[str], path: str, sitemap_paths: list[str]
) -> bool:
    if not sitemap_paths:
        errors.append("cannot prove custom 404 probe is absent without sitemap routes")
        return False
    if path in set(sitemap_paths):
        errors.append(f"custom 404 probe path collides with sitemap route: {path}")
        return False
    return True


def same_origin(left: str, right: str) -> bool:
    def origin(url: str) -> tuple[str, str | None, int | None]:
        parsed = urlparse(url)
        default_port = 443 if parsed.scheme.lower() == "https" else 80
        return parsed.scheme.lower(), parsed.hostname, parsed.port or default_port

    try:
        return origin(left) == origin(right)
    except ValueError:
        return False


def html_alias_redirects(html_authority: dict) -> list[tuple[str, str]]:
    """Return Pages' physical HTML aliases and their extensionless targets."""
    aliases: list[tuple[str, str]] = []
    custom_404 = html_authority.get("custom_404", {})
    custom_404_stem = None
    if isinstance(custom_404, dict):
        custom_output_path = custom_404.get("output_path")
        if isinstance(custom_output_path, str) and custom_output_path.endswith(".html"):
            custom_404_stem = f"/{custom_output_path[:-5]}"
    for item in html_authority.get("routes", []):
        if not isinstance(item, dict):
            continue
        output_path = item.get("output_path")
        request_path = item.get("request_path")
        if not isinstance(output_path, str) or not isinstance(request_path, str):
            continue
        if output_path == "index.html" or output_path.endswith("/index.html"):
            alias = f"/{output_path}"
            if alias != request_path:
                aliases.append((alias, request_path))
        if (
            request_path != "/"
            and request_path.endswith("/")
            and request_path[:-1] != custom_404_stem
        ):
            aliases.append((request_path[:-1], request_path))
    return sorted(set(aliases))


def asset_identity(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    return parsed.scheme.lower(), parsed.netloc.lower(), parsed.path


def collect_hashed_assets(
    errors: list[str],
    serving_root: str,
    page_url: str,
    body: str,
    canonical_root: str | None = None,
) -> list[tuple[str, str, str]]:
    canonical_root = canonical_root or serving_root
    parser = AssetParser()
    parser.feed(body)
    assets: list[tuple[str, str, str]] = []
    kinds = {kind for kind, _ in parser.references}
    for required_kind in ("CSS", "JavaScript"):
        if required_kind not in kinds:
            errors.append(
                f"{page_url}: no authored {required_kind} asset reference found"
            )
    for kind, reference in parser.references:
        try:
            resolved = urljoin(page_url, reference)
        except ValueError:
            errors.append(f"{page_url}: malformed {kind} asset URL: {reference!r}")
            continue
        if not (
            same_origin(serving_root, resolved) or same_origin(canonical_root, resolved)
        ):
            errors.append(
                f"{page_url}: external {kind} asset is not allowed: {reference!r}"
            )
            continue
        parsed = urlparse(resolved)
        if parsed.query or parsed.fragment:
            errors.append(
                f"{page_url}: {kind} asset must be query- and fragment-free: {reference!r}"
            )
            continue
        match = ADDRESSED_ASSET_RE.fullmatch(parsed.path)
        if match is None:
            errors.append(
                f"{page_url}: {kind} asset must use /a/<full-sha256>.<extension>: "
                f"{reference!r}"
            )
            continue
        expected_extension = ".css" if kind == "CSS" else ".js"
        if match.group(2).lower() != expected_extension:
            errors.append(
                f"{page_url}: {kind} asset has wrong extension {match.group(2)!r}: "
                f"{reference!r}"
            )
            continue
        # Authored absolute URLs intentionally name the canonical origin. Fetch
        # the identical physical path from the deployment origin under test so
        # an immutable Pages deployment and the custom domain are proved
        # independently from the same retained artifact.
        served_url = urljoin(serving_root.rstrip("/") + "/", parsed.path.lstrip("/"))
        assets.append((served_url, match.group(1), kind))
    return assets


def sitemap_html_paths(errors: list[str], site_root: str, body: bytes) -> list[str]:
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
    identities: dict[tuple[str, str, str], tuple[str, str]] = {}
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
            errors.append(
                f"conflicting duplicate authored asset reference: {asset_url!r}"
            )
        else:
            assets[asset_url] = (authored_hash, kind)
    return assets


def verify(
    base_url: str,
    timeout: float,
    expected_revision: str,
    release_manifest: dict,
    local_manifest_bytes: bytes,
    manifest_name: str,
    redirect_rules: list[RedirectRule],
    html_authority: dict,
    header_contract: HeaderContract,
    canonical_origin: str = CANONICAL_ORIGIN,
    require_cf_ray: bool = False,
    observed_colos: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    site_root = base_url.rstrip("/") + "/"
    canonical_root = canonical_origin.rstrip("/") + "/"
    responses: dict[str, tuple[int, dict[str, str], bytes]] = {}

    def fetch_exact(url: str) -> tuple[int, dict[str, str], bytes]:
        if url not in responses:
            responses[url] = request(url, timeout, follow=False)
            if require_cf_ray:
                ray = header(responses[url][1], "CF-Ray")
                match = CF_RAY_RE.fullmatch(ray)
                if match is None:
                    errors.append(f"{url}: missing or malformed exact CF-Ray: {ray!r}")
                elif observed_colos is not None:
                    observed_colos.add(match.group(1))
        return responses[url]

    resources_by_logical_path = {
        item["logical_path"]: item
        for item in release_manifest.get("resources", [])
        if isinstance(item, dict) and isinstance(item.get("logical_path"), str)
    }
    for required in REQUIRED_RELEASE_LOGICAL_PATHS:
        if required not in resources_by_logical_path:
            errors.append(f"local release manifest lacks required resource {required}")

    revision_url = urljoin(site_root, "build-revision.txt")
    revision_status, revision_headers, revision_body = fetch_exact(revision_url)
    if revision_status != 200:
        errors.append(
            f"/build-revision.txt returned {revision_status}, expected direct 200"
        )
    expected_body = f"{expected_revision}\n".encode()
    if revision_body != expected_body:
        errors.append(
            "deployed revision mismatch: "
            f"expected {expected_revision!r}, got {revision_body.decode('utf-8', errors='replace').strip()!r}"
        )
    validate_no_store_cache(errors, "/build-revision.txt", revision_headers)
    validate_live_direct_headers(
        errors,
        "/build-revision.txt",
        revision_headers,
        header_contract,
        exclude=frozenset({"cache-control"}),
    )

    manifest_url = urljoin(site_root, manifest_name)
    manifest_status, manifest_headers, manifest_body = fetch_exact(manifest_url)
    if manifest_status != 200:
        errors.append(
            f"/{manifest_name} returned {manifest_status}, expected direct 200"
        )
    validate_no_store_cache(errors, f"/{manifest_name}", manifest_headers)
    validate_live_direct_headers(
        errors,
        f"/{manifest_name}",
        manifest_headers,
        header_contract,
        exclude=frozenset({"cache-control"}),
    )
    if manifest_body != local_manifest_bytes:
        errors.append(
            f"live /{manifest_name} bytes differ from retained local artifact"
        )

    sitemap_url = urljoin(site_root, "sitemap.xml")
    sitemap_status, sitemap_headers, sitemap_body = fetch_exact(sitemap_url)
    if sitemap_status != 200:
        errors.append(f"/sitemap.xml returned {sitemap_status}, expected direct 200")
    validate_no_store_cache(errors, "/sitemap.xml", sitemap_headers)
    validate_live_direct_headers(
        errors,
        "/sitemap.xml",
        sitemap_headers,
        header_contract,
        exclude=frozenset({"cache-control"}),
    )
    html_paths = sitemap_html_paths(errors, canonical_root, sitemap_body)
    authority_by_path = {
        item["request_path"]: item
        for item in html_authority.get("routes", [])
        if isinstance(item, dict) and isinstance(item.get("request_path"), str)
    }
    sitemap_authority_paths = {
        item["request_path"]
        for item in html_authority.get("routes", [])
        if isinstance(item, dict)
        and item.get("in_sitemap") is True
        and isinstance(item.get("request_path"), str)
    }
    if sitemap_authority_paths != set(html_paths):
        errors.append(
            "live sitemap route set differs from retained HTML authority; "
            f"authority={sorted(sitemap_authority_paths)}, live={sorted(html_paths)}"
        )

    for item in release_manifest.get("resources", []):
        relative_url = item["request_url"]
        resource_url = urljoin(site_root, relative_url.lstrip("/"))
        if not same_origin(site_root, resource_url):
            errors.append(
                f"release manifest resource is not same-origin: {relative_url!r}"
            )
            continue
        status, resource_headers, body = fetch_exact(resource_url)
        directly_validated = item["output_path"] in {
            "build-revision.txt",
            "sitemap.xml",
        }
        if status != 200 and not directly_validated:
            errors.append(
                f"release resource {relative_url!r} returned {status}, expected direct 200"
            )
            continue
        if not directly_validated:
            validate_no_store_cache(
                errors, f"release resource {relative_url!r}", resource_headers
            )
        validate_live_direct_headers(
            errors,
            f"release resource {relative_url!r}",
            resource_headers,
            header_contract,
            exclude=frozenset({"cache-control"}),
        )
        if (
            release_manifest.get("media_types", {}).get(relative_url)
            == header_contract.speculation_content_type
        ):
            validate_speculation_content_type(
                errors,
                f"release resource {relative_url!r}",
                resource_headers,
                header_contract,
            )
        if item["output_path"] == "build-revision.txt":
            continue
        digest = hashlib.sha256(body).hexdigest()
        if digest != item["sha256"]:
            errors.append(
                f"release resource digest mismatch for {relative_url!r}: "
                f"expected {item['sha256']}, SHA-256={digest}"
            )

    pages: dict[str, str] = {}
    asset_references: list[tuple[str, str, str]] = []
    for path in sorted(authority_by_path):
        page_url = urljoin(site_root, path.lstrip("/"))
        status, headers, body_bytes = fetch_exact(page_url)
        body = body_bytes.decode("utf-8", errors="replace")
        if status != 200:
            errors.append(f"{path} returned {status}, expected direct 200")
        validate_html_boundary(errors, path, headers, body, header_contract)
        validate_html_content_type(errors, path, headers)
        canonical_url = urljoin(canonical_root, path.lstrip("/"))
        validate_canonical(errors, page_url, canonical_url, body)
        authority = authority_by_path.get(path)
        if authority is not None:
            digest = hashlib.sha256(body_bytes).hexdigest()
            if digest != authority["sha256"]:
                errors.append(
                    f"{path} body differs from retained HTML authority: "
                    f"expected {authority['sha256']}, SHA-256={digest}"
                )
        asset_references.extend(
            collect_hashed_assets(errors, site_root, page_url, body, canonical_root)
        )
        pages[path] = body

    for alias_path, target_path in html_alias_redirects(html_authority):
        alias_url = urljoin(site_root, alias_path.lstrip("/"))
        alias_status, alias_headers, _ = fetch_exact(alias_url)
        if alias_status != 308:
            errors.append(
                f"HTML alias {alias_path} returned {alias_status}, expected exact 308"
            )
        validate_html_boundary(
            errors, f"HTML alias {alias_path}", alias_headers, "", header_contract
        )
        location = header(alias_headers, "Location")
        expected_target = urljoin(site_root, target_path.lstrip("/"))
        resolved = urljoin(alias_url, location) if location else ""
        if not location:
            errors.append(f"HTML alias {alias_path} lacks Location")
        elif not same_origin(site_root, resolved):
            errors.append(
                f"HTML alias {alias_path} resolves outside the site: {resolved!r}"
            )
        elif resolved != expected_target:
            errors.append(
                f"HTML alias {alias_path} resolves to {resolved!r}, "
                f"expected {expected_target!r}"
            )

    missing_path = missing_probe_path(expected_revision)
    if missing_probe_is_disjoint(errors, missing_path, sorted(authority_by_path)):
        missing_url = urljoin(site_root, missing_path.lstrip("/"))
        missing_status, missing_headers, missing_bytes = fetch_exact(missing_url)
        missing_body = missing_bytes.decode("utf-8", errors="replace")
        if missing_status != 404:
            errors.append(
                f"{missing_path} returned {missing_status}, expected exact 404"
            )
        validate_html_boundary(
            errors, missing_path, missing_headers, missing_body, header_contract
        )
        validate_html_content_type(errors, missing_path, missing_headers)
        custom_authority = html_authority.get("custom_404", {})
        missing_digest = hashlib.sha256(missing_bytes).hexdigest()
        if missing_digest != custom_authority.get("sha256"):
            errors.append(
                f"{missing_path} body differs from retained custom-404 authority: "
                f"expected {custom_authority.get('sha256')!r}, SHA-256={missing_digest}"
            )
        for marker in CUSTOM_404_MARKERS:
            if marker not in missing_body:
                errors.append(f"{missing_path} lacks custom 404 marker {marker!r}")
        asset_references.extend(
            collect_hashed_assets(
                errors, site_root, missing_url, missing_body, canonical_root
            )
        )

    custom_authority = html_authority.get("custom_404", {})
    custom_digest = custom_authority.get("sha256")
    for item in release_manifest.get("resources", []):
        if item.get("cache_class") != "addressed":
            continue
        logical_path = item["logical_path"]
        alias_url = urljoin(site_root, logical_path)
        alias_status, alias_headers, alias_bytes = fetch_exact(alias_url)
        alias_body = alias_bytes.decode("utf-8", errors="replace")
        label = f"logical asset alias /{logical_path}"
        if alias_status != 404:
            errors.append(f"{label} returned {alias_status}, expected exact 404")
        validate_html_boundary(
            errors, label, alias_headers, alias_body, header_contract
        )
        validate_html_content_type(errors, label, alias_headers)
        alias_digest = hashlib.sha256(alias_bytes).hexdigest()
        if alias_digest != custom_digest:
            errors.append(
                f"{label} body differs from retained custom-404 authority: "
                f"expected {custom_digest!r}, SHA-256={alias_digest}"
            )

    evidence_body = pages.get("/evidence/", "")
    for marker in (
        'href="https://ardent.tools/evidence/"',
        "Evidence register",
        "0 published casts.",
    ):
        if marker not in evidence_body:
            errors.append(f"/evidence/ lacks deployment marker {marker!r}")

    assets = distinct_assets(errors, asset_references)
    manifest_urls = {
        urljoin(site_root, item["request_url"].lstrip("/"))
        for item in release_manifest.get("resources", [])
    }
    for asset_url, (authored_hash, kind) in assets.items():
        in_manifest = asset_url in manifest_urls
        if not in_manifest:
            errors.append(
                f"authored {kind} asset is absent from local release manifest: {asset_url!r}"
            )
        asset_status, asset_headers, asset_body = fetch_exact(asset_url)
        if asset_status != 200:
            if not in_manifest:
                errors.append(
                    f"authored {kind} asset {asset_url!r} returned {asset_status}, expected direct 200"
                )
            continue
        if not in_manifest:
            validate_no_store_cache(
                errors, f"authored {kind} asset {asset_url!r}", asset_headers
            )
        digest = hashlib.sha256(asset_body).hexdigest()
        if digest != authored_hash:
            errors.append(
                f"authored {kind} asset digest mismatch for {asset_url!r}: "
                f"path SHA-256={authored_hash}, body SHA-256={digest}"
            )

    for tombstone in release_manifest.get("tombstones", []):
        path = tombstone["path"]
        tombstone_url = urljoin(site_root, path.lstrip("/"))
        status, tombstone_headers, _ = fetch_exact(tombstone_url)
        if status not in (404, 410):
            errors.append(
                f"tombstone {path} returned {status}, expected direct 404 or 410"
            )
        validate_no_store_cache(errors, f"tombstone {path}", tombstone_headers)
        validate_live_direct_headers(
            errors,
            f"tombstone {path}",
            tombstone_headers,
            header_contract,
            exclude=frozenset({"cache-control"}),
        )

    for rule in redirect_rules:
        probe_path = redirect_probe_path(rule, expected_revision)
        probe_url = urljoin(site_root, probe_path.lstrip("/"))
        redirect_status, redirect_headers, _ = fetch_exact(probe_url)
        if redirect_status != rule.status:
            errors.append(
                f"redirect probe {probe_path} returned {redirect_status}, "
                f"expected exact {rule.status}"
            )
        location = header(redirect_headers, "Location")
        if not location:
            errors.append(f"redirect probe {probe_path} lacks Location")
            continue
        try:
            resolved = urljoin(probe_url, location)
        except ValueError:
            errors.append(
                f"redirect probe {probe_path} has malformed Location {location!r}"
            )
            continue
        expected_destination = urljoin(site_root, rule.target.lstrip("/"))
        if not same_origin(site_root, resolved):
            errors.append(
                f"redirect probe {probe_path} resolves outside the site: {resolved!r}"
            )
        if resolved != expected_destination:
            errors.append(
                f"redirect probe {probe_path} resolves to {resolved!r}, "
                f"expected {expected_destination!r}"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://ardent.tools")
    parser.add_argument(
        "--canonical-origin",
        default=CANONICAL_ORIGIN,
        help="canonical public HTTPS origin authored into retained documents",
    )
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--require-cf-ray",
        action="store_true",
        help="require every response to carry one exact Cloudflare colo receipt",
    )
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        required=True,
        help="exact retained public tree deployed by Wrangler",
    )
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")
    if not REVISION_RE.fullmatch(args.expected_revision):
        parser.error(
            "--expected-revision must be exactly one lowercase 40-hex revision"
        )
    try:
        validate_base_url(args.base_url)
        validate_base_url(args.canonical_origin)
    except ValueError as exc:
        parser.error(str(exc))
    contract, contract_errors = read_contract()
    if contract_errors:
        parser.error("; ".join(contract_errors))
    artifact_root = args.artifact_root.resolve()
    manifest_path = artifact_root / contract["manifest_name"]
    try:
        local_manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        parser.error(f"cannot read retained release manifest {manifest_path}: {exc}")
    release_manifest, manifest_errors = validate_manifest(
        local_manifest_bytes,
        output=artifact_root,
        expected_revision=args.expected_revision,
        contract=contract,
    )
    if manifest_errors:
        parser.error("invalid retained release manifest: " + "; ".join(manifest_errors))
    runtime_errors = validate_runtime(artifact_root)
    if runtime_errors:
        parser.error(
            "invalid retained Pages runtime boundary: " + "; ".join(runtime_errors)
        )
    authority_path = artifact_root / AUTHORITY_NAME
    try:
        authority_bytes = authority_path.read_bytes()
    except OSError as exc:
        parser.error(f"cannot read retained HTML authority {authority_path}: {exc}")
    html_authority, authority_errors = validate_authority(
        authority_bytes,
        output=artifact_root,
        expected_revision=args.expected_revision,
        base_url=args.canonical_origin,
    )
    if authority_errors:
        parser.error("invalid retained HTML authority: " + "; ".join(authority_errors))
    header_contract, header_errors = load_headers(
        artifact_root / "_headers", release_manifest
    )
    if header_errors or header_contract is None:
        parser.error("invalid retained header contract: " + "; ".join(header_errors))
    redirect_rules, redirect_errors = load_redirects(artifact_root / "_redirects")
    if redirect_errors:
        parser.error(
            "invalid retained redirect contract: " + "; ".join(redirect_errors)
        )

    last_errors: list[str] = []
    successful_colos: set[str] = set()
    for attempt in range(1, args.attempts + 1):
        attempt_colos: set[str] = set()
        try:
            last_errors = verify(
                args.base_url,
                args.timeout,
                args.expected_revision,
                release_manifest,
                local_manifest_bytes,
                contract["manifest_name"],
                redirect_rules,
                html_authority,
                header_contract,
                args.canonical_origin,
                args.require_cf_ray,
                attempt_colos,
            )
        except (OSError, URLError) as exc:
            last_errors = [f"request failed: {exc}"]
        if not last_errors:
            successful_colos = attempt_colos
            colo_receipt = (
                f"; Cloudflare colos={','.join(sorted(successful_colos))}"
                if successful_colos
                else ""
            )
            sys.stdout.write(
                f"PASS: production boundary verified on attempt {attempt}{colo_receipt}\n"
            )
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
