#!/usr/bin/env python3
"""Verify the authored/runtime boundary after a production deployment."""

from __future__ import annotations

import argparse
import re
import sys
import time
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class ScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            source = dict(attrs).get("src")
            if source:
                self.sources.append(source)


def request(url: str, timeout: float, follow: bool = True) -> tuple[int, dict[str, str], bytes]:
    opener = build_opener() if follow else build_opener(NoRedirect())
    req = Request(url, headers={"User-Agent": "ardent-tools-production-verifier/1"})
    try:
        with opener.open(req, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def header(headers: dict[str, str], name: str) -> str:
    return next((value for key, value in headers.items() if key.lower() == name.lower()), "")


def verify(base_url: str, timeout: float, expected_revision: str) -> list[str]:
    errors: list[str] = []
    revision_url = urljoin(base_url.rstrip("/") + "/", "build-revision.txt")
    revision_status, revision_headers, revision_body = request(revision_url, timeout)
    if revision_status != 200:
        errors.append(f"/build-revision.txt returned {revision_status}, expected 200")
    expected_body = f"{expected_revision}\n".encode()
    if revision_body != expected_body:
        errors.append(
            "deployed revision mismatch: "
            f"expected {expected_revision!r}, got {revision_body.decode('utf-8', errors='replace').strip()!r}"
        )
    revision_cache = {
        part.strip().lower()
        for part in header(revision_headers, "Cache-Control").split(",")
        if part.strip()
    }
    if "no-store" not in revision_cache:
        errors.append(
            f"/build-revision.txt Cache-Control is stale-capable: {header(revision_headers, 'Cache-Control')!r}"
        )

    evidence_url = urljoin(base_url.rstrip("/") + "/", "evidence/")
    status, headers, body_bytes = request(evidence_url, timeout)
    body = body_bytes.decode("utf-8", errors="replace")

    if status != 200:
        errors.append(f"/evidence/ returned {status}, expected 200")
    for marker in (
        'href="https://ardent.tools/evidence/"',
        "Evidence register",
        "0 published casts.",
    ):
        if marker not in body:
            errors.append(f"/evidence/ lacks deployment marker {marker!r}")

    cache_control = header(headers, "Cache-Control")
    if "no-transform" not in {part.strip().lower() for part in cache_control.split(",")}:
        errors.append(f"Cache-Control lacks no-transform: {cache_control!r}")

    csp = header(headers, "Content-Security-Policy")
    if "script-src 'self'" not in csp or "'unsafe-inline'" in csp or "wasm-unsafe-eval" in csp:
        errors.append(f"strict zero-cast CSP is absent: {csp!r}")

    if "/cdn-cgi/" in body or "__cf_email__" in body or "data-cfemail" in body:
        errors.append("Cloudflare email-protection markup/script was injected")

    scripts = ScriptParser()
    scripts.feed(body)
    expected_host = urlparse(base_url).hostname
    for source in scripts.sources:
        resolved = urlparse(urljoin(evidence_url, source))
        if resolved.hostname != expected_host:
            errors.append(f"remote script source found: {source}")
        if "/cdn-cgi/" in resolved.path:
            errors.append(f"Cloudflare decode script found: {source}")

    demos_url = urljoin(base_url.rstrip("/") + "/", "demos/")
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

    last_errors: list[str] = []
    for attempt in range(1, args.attempts + 1):
        try:
            last_errors = verify(args.base_url, args.timeout, args.expected_revision)
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
