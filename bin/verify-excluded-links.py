#!/usr/bin/env python3
"""Witness the github.com subpath links .lycheeignore excludes from lychee.

lychee 0.24.2's GitHub API fallback only ever queries GET /repos/{owner}/{repo}
- the bare root (lychee-lib/src/checker/website.rs:351-366). Any subpath
(blob/*, issues/*, ...) against a public repo runs unauthenticated against
github.com's own web frontend regardless of GITHUB_TOKEN, and 404s or
throttles independent of whether the target exists. .lycheeignore excludes
those exact URLs from lychee; this is what actually checks them, split by what
kind of fact each one is:

- This repository's own root files (LICENSE, LICENSE-DOCS, AI-USE-POLICY.md):
  checked against the local checkout, not a remote API call. The CI job
  already holds the exact commit under test on disk, so a filesystem check is
  a STRONGER witness than asking GitHub what the default branch's HEAD
  happens to hold at query time - no network, no rate limit, no token.
- A cross-repository fact this repo cannot hold locally (the akroasis issue
  content/systems/akroasis.md names): witnessed directly against the GitHub
  REST API, existence only (a 200 on the issue endpoint) - the same fact a
  resolving link would have proven, not its open/closed state.

Six more excluded links - the featured systems' own .kanon-ci.toml receipts in
content/systems/kanon.md - are witnessed by bin/validate-fleet-counts.py
instead, because that script already derives the exact repo/path list from
static/systems.json for its own fleet-count claims; duplicating that list here
would be a second copy of the same fact.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 15.0

# Source of the local-witness list: the repo's own root files that
# content/systems/kanon.md's neighbors (AI-USE-POLICY.md, LICENSE,
# LICENSE-DOCS) link to via a github.com/.../blob/main/<name> URL.
LOCAL_ROOT_FILES = ("AI-USE-POLICY.md", "LICENSE", "LICENSE-DOCS")

# Source of the remote-witness list: (owner, repo, issue number, site path
# that names it) for every cross-repo issue link .lycheeignore excludes.
REMOTE_ISSUES = (
    ("forkwright", "akroasis", 262, "content/systems/akroasis.md"),
)


def fetch(url: str, token: str | None) -> tuple[int | None, bytes]:
    """One GitHub REST API request. status None means the request never
    reached GitHub at all (DNS, TLS, connection failure)."""
    headers = {
        "User-Agent": "ardent-tools-excluded-link-witness/1",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as response:  # noqa: S310
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()
    except URLError as exc:
        return None, str(exc.reason).encode()


def check_local_files() -> list[str]:
    problems = []
    for name in LOCAL_ROOT_FILES:
        if not (ROOT / name).is_file():
            problems.append(
                f"{name}: not present at repository root, but "
                f"github.com/ardent-tools/ardent-tools-site/blob/main/{name} "
                "is linked from site copy"
            )
    return problems


def check_remote_issues(token: str | None) -> list[str]:
    problems = []
    for owner, repo, number, site_path in REMOTE_ISSUES:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}"
        status, body = fetch(url, token)
        if status is None:
            problems.append(
                f"UNVERIFIED: {owner}/{repo}#{number} ({site_path}): "
                f"GitHub API unreachable: {body.decode(errors='replace')}"
            )
        elif status == 403:
            problems.append(
                f"UNVERIFIED: {owner}/{repo}#{number} ({site_path}): "
                "GitHub API rate-limited or forbidden (403)"
            )
        elif status == 404:
            problems.append(
                f"{owner}/{repo}#{number} ({site_path}): GitHub reports 404 - "
                "issue not found or not visible to this token"
            )
        elif status != 200:
            problems.append(
                f"UNVERIFIED: {owner}/{repo}#{number} ({site_path}): "
                f"unexpected GitHub API status {status}"
            )
    return problems


def main() -> int:
    problems = check_local_files() + check_remote_issues(os.environ.get("GITHUB_TOKEN"))

    if problems:
        print(f"FAIL: {len(problems)} excluded-link witness problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(
        f"PASS: {len(LOCAL_ROOT_FILES)} local root file(s) present, "
        f"{len(REMOTE_ISSUES)} cross-repo issue(s) witnessed against the GitHub API"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
