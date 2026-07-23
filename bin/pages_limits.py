#!/usr/bin/env python3
"""Cloudflare Pages limits enforced at the repository release boundary."""

from __future__ import annotations

import stat
from pathlib import Path


MAX_STATIC_FILE_BYTES = 25 * 1024 * 1024
MAX_HEADER_RULES = 100
# The two fixed direct-response roots: "/*" (no-store default) and "/a/*"
# (immutable override for content-addressed resources).
ROOT_HEADER_RULES = 2
MAX_MEDIA_TYPE_HEADER_RULES = MAX_HEADER_RULES - ROOT_HEADER_RULES


def require_static_file_size(size: int, label: str) -> None:
    if size > MAX_STATIC_FILE_BYTES:
        raise ValueError(
            f"{label} exceeds Cloudflare Pages' {MAX_STATIC_FILE_BYTES}-byte "
            "static-file limit"
        )


def require_media_type_rule_capacity(count: int) -> None:
    total = ROOT_HEADER_RULES + count
    if total > MAX_HEADER_RULES:
        raise ValueError(
            "_headers would exceed Cloudflare Pages' "
            f"{MAX_HEADER_RULES}-rule limit: {ROOT_HEADER_RULES} root rules plus "
            f"{count} media-type rules"
        )


def validate_static_tree(root: Path) -> list[str]:
    """Return exact per-file size violations for a candidate Pages artifact."""
    errors: list[str] = []
    for path in sorted(root.rglob("*")):
        try:
            metadata = path.lstat()
        except OSError as exc:
            errors.append(f"Pages artifact metadata is unavailable for {path}: {exc}")
            continue
        if not stat.S_ISREG(metadata.st_mode):
            continue
        try:
            require_static_file_size(
                metadata.st_size,
                path.relative_to(root).as_posix(),
            )
        except ValueError as exc:
            errors.append(str(exc))
    return errors
