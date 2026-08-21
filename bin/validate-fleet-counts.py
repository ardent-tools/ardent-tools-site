#!/usr/bin/env python3
"""Prove the fleet counts stated in prose against an independent witness.

Usage: python3 bin/validate-fleet-counts.py

Three numbers appear in site copy - how many systems are featured, how many
public repositories the fleet holds, how many of the featured systems carry the
control-plane config. Each was hand-typed in more than one page, and a single
repository flipping visibility falsifies all three at once with nothing to catch
it.

The numbers stay in prose because a reader should meet them mid-sentence, not
follow a link. This proves them instead of deriving them into a template: the
copy is the surface, the catalog is the authority, and a disagreement fails the
gate.

A site whose subject is verification cannot carry an unverified count. That is
the specific self-refutation its own voice contract names.

Two legs. The first is consistency: the counts are derived from the catalog,
which every checkout has, so the copy is checked everywhere including CI. The
second is witness: the catalog's own `private` and `kanon_ci` fields are
authored in the same frontmatter the copy is checked against, so agreement
between them proves nothing about the repositories themselves. Every declared
public repository is checked directly against the GitHub API - real visibility,
and for featured systems, real presence of `.kanon-ci.toml` - not a second
reading of the same authored claim. A repository this cannot reach counts as
unwitnessed, not as agreement; this never reports PASS on an unwitnessed count.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "static/systems.json"
CONTROL_PLANE_CONFIG = ".kanon-ci.toml"
GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 15.0
REPO_URL_RE = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)$")

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20,
}
WORD_ALT = "|".join(NUMBER_WORDS)

# Each claim: a regex over site copy with one capture group holding the number,
# and the name of the derived value it must equal. The regex is deliberately
# tight - a loose pattern that stops matching after a rewrite reports success
# for a claim it is no longer reading.
CLAIMS = (
    # Tight on purpose. "Two systems are the exception - they belong to my prior
    # employer" is a different claim about ownership, and a pattern loose enough
    # to catch the fleet count catches that too. Rewording the real sentence
    # makes this stop matching, which the zero-match guard below turns into a
    # failure rather than a silent pass.
    ("featured_systems",
     re.compile(rf"\b({WORD_ALT})\s+systems,\s+the\s+libraries", re.I)),
    ("public_repos", re.compile(rf"\b({WORD_ALT})\s+public\s+repositor", re.I)),
    ("featured_public_with_control_plane",
     re.compile(rf"\b({WORD_ALT})\s+featured\s+public\s+system\s+repositor", re.I)),
)


def derive() -> dict[str, int]:
    """Ground truth for the stated counts, from the derived catalog.

    Every checkout has the catalog, so all three counts resolve in CI. This is
    the consistency leg - it proves the copy agrees with the catalog, not that
    the catalog agrees with reality. `witness()` is the leg that does that.
    """
    systems = json.loads(CATALOG.read_text())["systems"]

    featured = [s for s in systems if s.get("group") == "systems"]
    public = [s for s in systems if not s.get("private")]
    featured_public = [s for s in featured if not s.get("private")]

    return {
        "featured_systems": len(featured),
        "public_repos": len(public),
        "featured_public_with_control_plane":
            sum(1 for s in featured_public if s.get("kanon_ci")),
    }


FETCH_ATTEMPTS = 3
FETCH_BACKOFF_SECONDS = 2.0


def fetch_once(url: str, token: str | None) -> tuple[int | None, bytes]:
    """One GitHub REST API request. Isolated so tests can replace it with a
    fixture instead of reaching the network; status None means the request
    never reached GitHub at all (DNS, TLS, connection failure)."""
    headers = {
        "User-Agent": "ardent-tools-fleet-count-witness/1",
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


def fetch(url: str, token: str | None) -> tuple[int | None, bytes]:
    """`fetch_once` with bounded retries on a 5xx, which is GitHub being briefly
    unavailable rather than an answer about the repository.

    WHY only 5xx: every other outcome is informative and must not be retried. A 404
    means the repo is absent or invisible to this token, a 403 means rate-limited, and
    a None means the request never reached GitHub -- retrying those spends time to
    re-learn the same fact. A 5xx is the one status that says nothing about the
    subject, and the gate previously turned a single one into a hard UNVERIFIED that
    failed the deploy. Observed: `unexpected GitHub API status 504` on one repository
    during a GitHub degradation, red-lining a branch whose own content was fine.

    WHY it still fails closed when the retries are exhausted: this witness exists so a
    public numeric claim is checked against reality, and a claim nobody could verify is
    not a claim that passed. The retry removes the transient failure, not the contract.
    """
    status, body = fetch_once(url, token)
    for attempt in range(1, FETCH_ATTEMPTS):
        if status is None or status < 500:
            return status, body
        time.sleep(FETCH_BACKOFF_SECONDS * attempt)
        status, body = fetch_once(url, token)
    return status, body


def witness_repo(
    owner: str, repo: str, *, check_kanon_ci: bool, token: str | None
) -> tuple[bool | None, bool | None, str | None]:
    """Ask GitHub directly what one fleet repository's own state is.

    Returns (actual_private, actual_kanon_ci, error). `actual_kanon_ci` stays
    None when `check_kanon_ci` is False - the contents lookup would cost an API
    call to answer a fact this claim set does not use. A non-None `error` means
    neither field was witnessed, regardless of what the tuple otherwise carries.
    """
    status, body = fetch(f"{GITHUB_API}/repos/{owner}/{repo}", token)
    if status is None:
        return None, None, f"GitHub API unreachable: {body.decode(errors='replace')}"
    if status == 403:
        return None, None, "GitHub API rate-limited or forbidden (403)"
    if status == 404:
        return None, None, "repository not found or not visible to this token (404)"
    if status != 200:
        return None, None, f"unexpected GitHub API status {status}"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return None, None, f"GitHub API returned non-JSON: {exc}"
    if not isinstance(payload, dict) or not isinstance(payload.get("private"), bool):
        return None, None, "GitHub API response missing a boolean 'private' field"
    actual_private = payload["private"]

    if not check_kanon_ci:
        return actual_private, None, None

    ci_status, ci_body = fetch(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{CONTROL_PLANE_CONFIG}", token
    )
    if ci_status == 200:
        return actual_private, True, None
    if ci_status == 404:
        return actual_private, False, None
    if ci_status is None:
        return actual_private, None, (
            f"GitHub API unreachable checking {CONTROL_PLANE_CONFIG}: "
            f"{ci_body.decode(errors='replace')}"
        )
    return actual_private, None, (
        f"unexpected GitHub API status {ci_status} checking {CONTROL_PLANE_CONFIG}"
    )


def witness(systems: list[dict], token: str | None) -> tuple[list[str], int]:
    """Independent GitHub-sourced ground truth for repository visibility and
    control-plane adoption - the two facts `derive()` can only read from the
    same authored frontmatter the copy itself is checked against. Every
    catalog entry naming a repository is checked, public or declared private,
    so a repository quietly flipped either direction is caught either way. An
    entry declared public with no 'repo' field at all still contributes to
    `derive()`'s counts, so it is UNVERIFIED rather than silently skipped - a
    declared-private entry with no repo contributes to nothing and is skipped.
    """
    problems: list[str] = []
    checked = 0

    for s in systems:
        repo_url = s.get("repo")
        declared_private = bool(s.get("private", False))
        if not repo_url:
            # A private entry with no repo field never contributes to any
            # derived count (derive() only counts `not private`), so there is
            # nothing here that needs witnessing. A public entry with no repo
            # DOES contribute to public_repos - and to the control-plane
            # count too when featured - so skipping it silently would let an
            # entry inflate the trusted counts while never being checked
            # against anything. That must be UNVERIFIED, not skipped.
            if not declared_private:
                problems.append(
                    f"UNVERIFIED: {s['name']}: catalog declares this public "
                    "but has no 'repo' field to witness it against GitHub"
                )
            continue
        match = REPO_URL_RE.fullmatch(repo_url)
        if not match:
            problems.append(
                f"{s['name']}: repo URL {repo_url!r} is not an exact "
                "https://github.com/<owner>/<repo> form"
            )
            continue
        owner, repo = match.groups()
        check_ci = s.get("group") == "systems"
        actual_private, actual_kanon_ci, error = witness_repo(
            owner, repo, check_kanon_ci=check_ci, token=token
        )
        if error:
            problems.append(f"UNVERIFIED: {s['name']} ({owner}/{repo}): {error}")
            continue
        checked += 1

        if actual_private != declared_private:
            problems.append(
                f"{s['name']}: catalog declares private={declared_private} but "
                f"GitHub reports {owner}/{repo} private={actual_private}"
            )
        if check_ci:
            declared_ci = bool(s.get("kanon_ci", False))
            if actual_kanon_ci != declared_ci:
                problems.append(
                    f"{s['name']}: catalog declares kanon_ci={declared_ci} but "
                    f"GitHub shows {CONTROL_PLANE_CONFIG} is "
                    f"{'present' if actual_kanon_ci else 'absent'} in {owner}/{repo}"
                )

    if checked == 0:
        problems.append(
            "UNVERIFIED: no repository was witnessed against GitHub - either the "
            "catalog lost its repo fields or the witness stopped running"
        )

    return problems, checked


def surfaces() -> list[Path]:
    out = []
    for pattern in ("content/**/*.md",):
        out.extend(p for p in ROOT.glob(pattern) if p.is_file())
    return sorted(out)


def main() -> int:
    if not CATALOG.is_file():
        print(f"FAIL: {CATALOG.relative_to(ROOT)} missing; run "
              "`python3 bin/site.py sync` first", file=sys.stderr)
        return 1

    truth = derive()
    systems = json.loads(CATALOG.read_text())["systems"]
    problems, witnessed = witness(systems, os.environ.get("GITHUB_TOKEN"))
    seen: dict[str, int] = {name: 0 for name, _ in CLAIMS}

    for path in surfaces():
        text = path.read_text(errors="replace")
        rel = path.relative_to(ROOT)
        for name, rx in CLAIMS:
            for m in rx.finditer(text):
                seen[name] += 1
                stated = NUMBER_WORDS[m.group(1).lower()]
                if stated != truth[name]:
                    line = text[: m.start()].count("\n") + 1
                    problems.append(
                        f"{rel}:{line} states {m.group(1)} for {name}; "
                        f"derived value is {truth[name]}")

    # A claim nobody states is not proof of health - it means the regex has
    # stopped reading the copy, which is the failure this check exists to avoid.
    for name, count in seen.items():
        if count == 0:
            problems.append(
                f"no surface states `{name}` - either the copy was rewritten and "
                "this validator no longer reads it, or the claim was dropped. "
                f"Derived value is {truth[name]}.")

    for name, value in truth.items():
        print(f"  {name} = {value} ({seen[name]} statement(s) in copy)")
    print(f"  {witnessed} repositor{'y' if witnessed == 1 else 'ies'} witnessed "
          "directly against the GitHub API")

    if problems:
        print(f"\nFAIL: {len(problems)} fleet-count problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print("PASS: fleet counts in copy agree with the derived catalog and are "
          "witnessed against GitHub")
    return 0


if __name__ == "__main__":
    sys.exit(main())
