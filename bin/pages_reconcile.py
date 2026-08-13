#!/usr/bin/env python3
"""Reconcile actual Cloudflare Pages state after an attempted mutation.

Scans a freshly captured Cloudflare deployments-list snapshot (paginated
`GET .../pages/projects/<project>/deployments`, taken AFTER the preview and
promote attempts run) for entries Cloudflare itself recorded for this exact
run's commit and branch, and emits GITHUB_OUTPUT-formatted `key=value`
lines: `preview_accepted`, `preview_deployment_ids` (comma-joined, may be
more than one if a prior run's cleanup was itself interrupted), and
`production_accepted`.

WHY this exists instead of trusting a step's own outcome (AT-02): a
`wrangler pages deploy` call can be accepted by Cloudflare and then have its
client-side process fail on a transport hiccup or receipt-parse error,
which fails that workflow step even though the mutation landed. Reading
`steps.<id>.outcome` after that conflates "our local script errored" with
"Cloudflare's state changed" - the two are independent facts. This module
answers only the second question, by asking Cloudflare directly, so preview
cleanup and production restore can act on what actually happened rather
than on how loudly the client failed. It never inspects step outcomes,
receipts, or GITHUB_ENV - only the deployment list itself.

A commit+branch match is required (not commit hash alone): environment,
project_name, and deployment_trigger.metadata.{commit_hash,branch} together
are the only Cloudflare-side facts this exact run's mutation could have
produced. Schema verified against
https://developers.cloudflare.com/api/resources/pages/subresources/projects/subresources/deployments/methods/list/.
"""

from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path

from pages_deployment_receipt import validate_branch_name
from pages_last_deployment import (
    DEPLOYMENT_ID_RE,
    MAX_LIST_BYTES,
    PROJECT_RE,
    REVISION_RE,
    strict_array,
)


def _matches(
    entry: object, *, environment: str, project: str, revision: str, branch: str
) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("environment") != environment:
        return False
    if entry.get("project_name") != project:
        return False
    trigger = entry.get("deployment_trigger")
    trigger_metadata = trigger.get("metadata") if isinstance(trigger, dict) else None
    if not isinstance(trigger_metadata, dict):
        return False
    if trigger_metadata.get("commit_hash") != revision:
        return False
    return trigger_metadata.get("branch") == branch


def reconcile(
    path: Path,
    *,
    project: str,
    revision: str,
    preview_branch: str,
    production_branch: str = "main",
) -> tuple[list[str], bool]:
    """Return (preview_deployment_ids, production_accepted) for this run.

    `preview_deployment_ids` lists every preview deployment Cloudflare
    recorded for this exact commit+branch (normally zero or one; more than
    one means an earlier run's cleanup never completed, and every one of
    them is still a real public preview that must be deleted).
    `production_accepted` is True iff Cloudflare recorded a production
    deployment for this exact commit+branch, independent of whether any
    later verification of it passed.
    """
    if not PROJECT_RE.fullmatch(project):
        raise ValueError("Pages project name is invalid")
    if not REVISION_RE.fullmatch(revision):
        raise ValueError("revision must be one lowercase 40-hex value")
    validate_branch_name(preview_branch, label="preview")
    validate_branch_name(production_branch, label="production")
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

    preview_ids: list[str] = []
    for entry in deployments:
        if not _matches(
            entry,
            environment="preview",
            project=project,
            revision=revision,
            branch=preview_branch,
        ):
            continue
        deployment_id = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(deployment_id, str) or not DEPLOYMENT_ID_RE.fullmatch(
            deployment_id
        ):
            raise ValueError("matched preview deployment id is not one lowercase UUID")
        preview_ids.append(deployment_id)

    production_accepted = any(
        _matches(
            entry,
            environment="production",
            project=project,
            revision=revision,
            branch=production_branch,
        )
        for entry in deployments
    )
    return preview_ids, production_accepted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("deployments", type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--preview-branch", required=True)
    parser.add_argument("--production-branch", default="main")
    args = parser.parse_args()
    try:
        preview_ids, production_accepted = reconcile(
            args.deployments,
            project=args.project,
            revision=args.revision,
            preview_branch=args.preview_branch,
            production_branch=args.production_branch,
        )
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1
    sys.stdout.write(f"preview_accepted={'true' if preview_ids else 'false'}\n")
    sys.stdout.write(f"preview_deployment_ids={','.join(preview_ids)}\n")
    sys.stdout.write(
        f"production_accepted={'true' if production_accepted else 'false'}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
