#!/usr/bin/env python3
"""Extract one exact immutable Pages deployment URL from Wrangler JSONL."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path
from urllib.parse import urlparse

MAX_RECEIPT_BYTES = 1024 * 1024
MAX_RECEIPT_LINES = 128
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
PROJECT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,255}$")
DEPLOYMENT_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
DEPLOYMENT_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def strict_object(raw: str, label: str) -> dict:
    def reject_constant(value: str) -> None:
        raise ValueError(f"{label}: non-finite JSON constant {value!r}")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label}: duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ValueError(f"{label}: not strict JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}: entry must be an object")
    return value


def validate_url(value: object, project: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Wrangler deployment URL must be a string")
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Wrangler deployment URL is malformed: {exc}") from exc
    hostname = parsed.hostname or ""
    suffix = f".{project}.pages.dev"
    label = hostname.removesuffix(suffix) if hostname.endswith(suffix) else ""
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or not DEPLOYMENT_LABEL_RE.fullmatch(label)
        or value != f"https://{label}{suffix}"
    ):
        raise ValueError(
            "Wrangler deployment URL must be one immutable lowercase HTTPS "
            f"<deployment>.{project}.pages.dev origin"
        )
    return value


def extract_deployment_url(
    path: Path, *, expected_revision: str, project: str, production_branch: str
) -> str:
    if not REVISION_RE.fullmatch(expected_revision):
        raise ValueError("expected revision must be one lowercase 40-hex value")
    if not PROJECT_RE.fullmatch(project):
        raise ValueError("Pages project name is invalid")
    if (
        not BRANCH_RE.fullmatch(production_branch)
        or production_branch.startswith(("/", "."))
        or "//" in production_branch
        or ".." in production_branch.split("/")
    ):
        raise ValueError("production branch name is invalid")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError(f"cannot inspect Wrangler output receipt: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Wrangler output receipt must be one regular non-symlink file")
    if metadata.st_size < 1 or metadata.st_size > MAX_RECEIPT_BYTES:
        raise ValueError(
            f"Wrangler output receipt size must be 1..{MAX_RECEIPT_BYTES} bytes"
        )
    try:
        raw = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Wrangler output receipt is not strict UTF-8: {exc}") from exc
    if not raw.endswith("\n") or "\r" in raw or "\x00" in raw:
        raise ValueError("Wrangler output receipt must be LF-terminated JSONL")
    lines = raw.splitlines()
    if not 1 <= len(lines) <= MAX_RECEIPT_LINES or any(not line for line in lines):
        raise ValueError(
            f"Wrangler output receipt must contain 1..{MAX_RECEIPT_LINES} nonempty lines"
        )
    entries = [
        strict_object(line, f"Wrangler output line {index}")
        for index, line in enumerate(lines, start=1)
    ]
    detailed = [
        entry for entry in entries if entry.get("type") == "pages-deploy-detailed"
    ]
    if len(detailed) != 1:
        raise ValueError(
            "Wrangler output must contain exactly one pages-deploy-detailed entry"
        )
    entry = detailed[0]
    if type(entry.get("version")) is not int or entry["version"] != 1:
        raise ValueError("Wrangler detailed deployment receipt must use version 1")
    if entry.get("pages_project") != project:
        raise ValueError("Wrangler detailed deployment project differs")
    deployment_id = entry.get("deployment_id")
    if not isinstance(deployment_id, str) or not DEPLOYMENT_ID_RE.fullmatch(
        deployment_id
    ):
        raise ValueError("Wrangler detailed deployment_id is not one lowercase UUID")
    if entry.get("environment") != "production":
        raise ValueError("Wrangler detailed deployment environment is not production")
    if entry.get("production_branch") != production_branch:
        raise ValueError("Wrangler detailed deployment production branch differs")
    trigger = entry.get("deployment_trigger")
    metadata_value = trigger.get("metadata") if isinstance(trigger, dict) else None
    commit_hash = (
        metadata_value.get("commit_hash") if isinstance(metadata_value, dict) else None
    )
    if commit_hash != expected_revision:
        raise ValueError("Wrangler detailed deployment commit hash differs")
    deployment_url = validate_url(entry.get("url"), project)

    basic = [entry for entry in entries if entry.get("type") == "pages-deploy"]
    if len(basic) != 1:
        raise ValueError("Wrangler output must contain exactly one pages-deploy entry")
    basic_entry = basic[0]
    if (
        type(basic_entry.get("version")) is not int
        or basic_entry["version"] != 1
        or basic_entry.get("pages_project") != project
        or basic_entry.get("deployment_id") != deployment_id
        or basic_entry.get("url") != deployment_url
    ):
        raise ValueError("Wrangler basic and detailed deployment receipts differ")
    return deployment_url


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--production-branch", default="main")
    args = parser.parse_args()
    try:
        url = extract_deployment_url(
            args.receipt,
            expected_revision=args.expected_revision,
            project=args.project,
            production_branch=args.production_branch,
        )
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1
    sys.stdout.write(f"{url}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
