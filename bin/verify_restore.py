#!/usr/bin/env python3
"""Confirm the canonical domain reports a specific revision after a
Cloudflare Pages rollback.

Unlike bin/verify-production.py, this performs no local-artifact
comparison. After an AT-01 auto-restore, the live site serves a PRIOR
revision's bytes, while this job's checked-out worktree and built public/
tree only hold manifests for the revision that just failed canonical
verification (do not pass this build's public/ tree to verify-production.py
as evidence about a different, older revision - its --expected-revision is
validated against the LOCAL retained manifest's own baked-in revision and
would reject its own artifact-root before ever making a request).

This script proves exactly two things: the canonical origin answers, and
its self-reported build-revision.txt matches the restored deployment. Deep
header/asset/route verification of a rolled-back revision would require
rebuilding that prior commit from source, which the auto-restore path
deliberately does not do.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


def fetch(url: str, timeout: float) -> tuple[int, bytes]:
    req = Request(url, headers={"User-Agent": "ardent-tools-restore-verifier/1"})
    try:
        with urlopen(req, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def verify_once(base_url: str, expected_revision: str, timeout: float) -> list[str]:
    errors: list[str] = []
    root_status, _ = fetch(base_url.rstrip("/") + "/", timeout)
    if root_status != 200:
        errors.append(f"{base_url} root path returned {root_status}, expected 200")
    revision_url = base_url.rstrip("/") + "/build-revision.txt"
    revision_status, revision_body = fetch(revision_url, timeout)
    if revision_status != 200:
        errors.append(
            f"{revision_url} returned {revision_status}, expected direct 200"
        )
    expected_body = f"{expected_revision}\n".encode()
    if revision_body != expected_body:
        errors.append(
            "restored revision mismatch: expected "
            f"{expected_revision!r}, got "
            f"{revision_body.decode('utf-8', errors='replace').strip()!r}"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--attempts", type=int, default=13)
    parser.add_argument("--delay", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    if not REVISION_RE.fullmatch(args.expected_revision):
        parser.error(
            "--expected-revision must be exactly one lowercase 40-hex revision"
        )
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")

    last_errors: list[str] = []
    for attempt in range(1, args.attempts + 1):
        try:
            last_errors = verify_once(
                args.base_url, args.expected_revision, args.timeout
            )
        except (OSError, URLError) as exc:
            last_errors = [f"request failed: {exc}"]
        if not last_errors:
            sys.stdout.write(
                f"PASS: {args.base_url} reports restored revision "
                f"{args.expected_revision} on attempt {attempt}\n"
            )
            return 0
        if attempt < args.attempts:
            sys.stderr.write(
                f"attempt {attempt}/{args.attempts} not yet restored: "
                f"{'; '.join(last_errors)}\n"
            )
            time.sleep(args.delay)

    for error in last_errors:
        sys.stderr.write(f"ERROR: {error}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
