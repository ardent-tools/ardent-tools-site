#!/usr/bin/env python3
"""Extract the last-known-good production Pages deployment id + commit sha.

Parses a JSON array of Cloudflare Pages deployment objects (the paginated
`GET .../pages/projects/<project>/deployments` response, combined and
captured to a file by the caller) and emits GITHUB_OUTPUT-formatted
`key=value` lines: `had_prior_deployment`, plus `last_good_deployment_id`
and `last_good_revision` when a prior production deployment exists.
`wrangler pages deployment list --json` is NOT this input - its PascalCase
display mapping fails validation here by design; see
`test_wrangler_pascal_case_shape_is_rejected`.

WHY a project's first-ever production deploy is not an error: there is no
last-known-good to roll back to yet. The AT-01 auto-restore workflow step
consumes `had_prior_deployment` to skip the rollback call itself, not to
fail this extraction.

WHY the newest production entry is not enough (AT-02): `environment ==
"production"` alone proves nothing about whether that deployment actually
succeeded, ran at all, or belongs to this project. A candidate must also
carry `latest_stage.status == "success"`, `is_skipped == false`, and
`project_name` matching the trusted `--project` authority. A production
history that exists but contains no such candidate (all failed, all
skipped, or misattributed) fails closed rather than silently promoting a
newer bad entry or falling back to an older one that was never verified as
selectable - see `extract_last_good`. Schema verified against
https://developers.cloudflare.com/api/resources/pages/subresources/projects/subresources/deployments/methods/list/.
"""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path

MAX_LIST_BYTES = 4 * 1024 * 1024
PROJECT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
DEPLOYMENT_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def strict_array(raw: str) -> list:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value!r}")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw, parse_constant=reject_constant, object_pairs_hook=reject_duplicates
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ValueError(f"deployment list is not strict JSON: {exc}") from exc
    # WHY: `wrangler ... --json` has been observed elsewhere to print either
    # a bare result array or the full CF API envelope depending on command
    # and version; accept both shapes explicitly rather than guessing
    # silently. UNVERIFIED against a live wrangler 4.112.0 run - see AT-01
    # report.
    if isinstance(value, dict) and isinstance(value.get("result"), list):
        value = value["result"]
    if not isinstance(value, list):
        raise ValueError("deployment list must be a JSON array (or {result: [...]})")
    return value


def extract_last_good(path: Path, *, project: str) -> tuple[str | None, str | None]:
    if not PROJECT_RE.fullmatch(project):
        raise ValueError("Pages project name is invalid")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError(f"cannot inspect deployment list receipt: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("deployment list receipt must be one regular non-symlink file")
    if metadata.st_size < 1 or metadata.st_size > MAX_LIST_BYTES:
        raise ValueError(
            f"deployment list receipt size must be 1..{MAX_LIST_BYTES} bytes"
        )
    try:
        raw = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"deployment list receipt is not strict UTF-8: {exc}") from exc
    deployments = strict_array(raw)
    production_entries = [
        entry
        for entry in deployments
        if isinstance(entry, dict) and entry.get("environment") == "production"
    ]
    if not production_entries:
        # WHY this is not an error: a genuinely empty production history is
        # a first-ever deploy, not an ambiguous state - there is nothing to
        # have rolled back to.
        return None, None

    def is_explicit_successful_non_skipped(entry: dict) -> bool:
        if entry.get("project_name") != project:
            return False
        if entry.get("is_skipped") is not False:
            return False
        latest_stage = entry.get("latest_stage")
        return (
            isinstance(latest_stage, dict) and latest_stage.get("status") == "success"
        )

    candidates = [
        entry for entry in production_entries if is_explicit_successful_non_skipped(entry)
    ]
    if not candidates:
        # WHY this raises instead of returning (None, None): production
        # history exists but nothing in it qualifies (all failed/active/
        # skipped, or none attributed to this project) - that is ambiguous,
        # not "no prior deployment", so it must fail before promotion
        # rather than silently proceed unprotected.
        raise ValueError(
            "no explicit successful, non-skipped, canonical-production "
            f"deployment found for project {project!r}"
        )

    def created_on(entry: dict) -> str:
        value = entry.get("created_on")
        return value if isinstance(value, str) else ""

    candidates.sort(key=created_on, reverse=True)
    newest = candidates[0]
    deployment_id = newest.get("id")
    if not isinstance(deployment_id, str) or not DEPLOYMENT_ID_RE.fullmatch(
        deployment_id
    ):
        raise ValueError("newest production deployment id is not one lowercase UUID")
    trigger = newest.get("deployment_trigger")
    trigger_metadata = trigger.get("metadata") if isinstance(trigger, dict) else None
    commit_hash = (
        trigger_metadata.get("commit_hash")
        if isinstance(trigger_metadata, dict)
        else None
    )
    if not isinstance(commit_hash, str) or not REVISION_RE.fullmatch(commit_hash):
        raise ValueError(
            "newest production deployment commit hash is not one lowercase 40-hex value"
        )
    return deployment_id, commit_hash


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("deployments", type=Path)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        deployment_id, revision = extract_last_good(
            args.deployments, project=args.project
        )
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1
    if deployment_id is None:
        sys.stdout.write("had_prior_deployment=false\n")
        return 0
    sys.stdout.write("had_prior_deployment=true\n")
    sys.stdout.write(f"last_good_deployment_id={deployment_id}\n")
    sys.stdout.write(f"last_good_revision={revision}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
